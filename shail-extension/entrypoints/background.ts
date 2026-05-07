import { api } from '../src/lib/api';
import type {
  BackgroundMessage,
  BackgroundResponse,
  SitePolicy,
} from '../src/types/contracts';

// ─── Storage keys ─────────────────────────────────────────────────────────────

const KEY_POLICIES      = 'shail_policies';
const KEY_CAPTURE       = 'shail_capture_enabled';
const KEY_DOC_INDEX     = 'shail_doc_index';      // local list of saved document IDs
const MAX_INDEX_SIZE    = 200;                     // keep last 200 documents

// ─── Local document index ─────────────────────────────────────────────────────

interface DocIndexEntry {
  id:        string;
  customId?: string;   // SHA-256 fingerprint — used for exact dedup before API call
  sourceApp: string;
  sourceUrl: string;
  title:     string;
  timestamp: string;
  eventType: string;
}

async function storeDocumentId(docId: string, payload: import('../src/types/contracts').CaptureCandidate): Promise<void> {
  const result = await browser.storage.local.get(KEY_DOC_INDEX);
  const index: DocIndexEntry[] = (result[KEY_DOC_INDEX] as DocIndexEntry[]) ?? [];

  // Avoid duplicates
  if (index.some(e => e.id === docId)) return;

  index.unshift({
    id:        docId,
    customId:  payload.customId,   // store fingerprint for pre-API dedup
    sourceApp: payload.sourceApp,
    sourceUrl: payload.sourceUrl,
    title:     payload.title ?? '',
    timestamp: payload.timestamp,
    eventType: payload.eventType,
  });

  // Keep max 200
  if (index.length > MAX_INDEX_SIZE) index.splice(MAX_INDEX_SIZE);

  // Also update shail_recent_saves so popup dedup check is instant on next open
  const recResult = await browser.storage.local.get('shail_recent_saves');
  const recSaves = (recResult['shail_recent_saves'] as Array<{ url: string; timestamp: string }>) ?? [];
  recSaves.unshift({ url: payload.sourceUrl, timestamp: payload.timestamp });

  await browser.storage.local.set({
    [KEY_DOC_INDEX]: index,
    shail_recent_saves: recSaves.slice(0, 200),
  });
}

// ─── Badge helpers ────────────────────────────────────────────────────────────

let badgeClearTimer: ReturnType<typeof setTimeout> | null = null;

function showCaptureBadge() {
  browser.action.setBadgeText({ text: '✓' });
  browser.action.setBadgeBackgroundColor({ color: '#22c55e' });
  if (badgeClearTimer) clearTimeout(badgeClearTimer);
  badgeClearTimer = setTimeout(() => {
    browser.action.setBadgeText({ text: '' });
  }, 3000);
}

function showErrorBadge() {
  browser.action.setBadgeText({ text: '!' });
  browser.action.setBadgeBackgroundColor({ color: '#ef4444' });
  if (badgeClearTimer) clearTimeout(badgeClearTimer);
  badgeClearTimer = setTimeout(() => {
    browser.action.setBadgeText({ text: '' });
  }, 4000);
}

// ─── Storage helpers ──────────────────────────────────────────────────────────

async function getCaptureEnabled(): Promise<boolean> {
  const result = await browser.storage.local.get(KEY_CAPTURE);
  return (result[KEY_CAPTURE] as boolean) ?? true;
}

async function getCachedPolicies(): Promise<SitePolicy[]> {
  const result = await browser.storage.local.get(KEY_POLICIES);
  return (result[KEY_POLICIES] as SitePolicy[]) ?? [];
}

// ─── Policy check ─────────────────────────────────────────────────────────────

function isDomainDenied(url: string, policies: SitePolicy[]): boolean {
  try {
    const hostname = new URL(url).hostname;
    const match = policies.find(p =>
      hostname === p.domain || hostname.endsWith(`.${p.domain}`)
    );
    return match?.policy === 'DENY';
  } catch {
    return false;
  }
}

// ─── Message handler ──────────────────────────────────────────────────────────

async function handleMessage(
  message: BackgroundMessage,
  sender: chrome.runtime.MessageSender,
): Promise<BackgroundResponse> {
  switch (message.type) {
    case 'CAPTURE': {
      // ── Dedup: check local index before hitting the API ────────────────────
      // Two signals:
      //   1. customId match   — exact same capture (url + date + content hash)
      //   2. sourceUrl match  — same web page already saved on a previous day
      //      (web page captures only; AI convos on the same URL differ by content)
      {
        const dupStored = await browser.storage.local.get(KEY_DOC_INDEX);
        const dupIndex  = (dupStored[KEY_DOC_INDEX] as DocIndexEntry[]) ?? [];
        const { customId, sourceUrl, eventType } = message.payload;

        // conversationId captures use a stable customId per conversation.
        // Backend handles upsert idempotently — skip the local ring for these.
        const hasConversationId = !!(message.payload as { conversationId?: string }).conversationId;

        const isDuplicate =
          !hasConversationId && (
            // Exact fingerprint match (covers all event types)
            (customId && dupIndex.some(e => e.customId === customId)) ||
            // URL match for page visits (same page across different days)
            (eventType === 'page_visit' &&
              dupIndex.some(e => e.sourceUrl === sourceUrl && e.eventType === 'page_visit'))
          );

        if (isDuplicate) {
          return { ok: true, data: { status: 'duplicate' } };
        }
      }

      // AI content scripts now score content before sending CAPTURE, so only
      // genuinely valuable content reaches here. Keep a safety floor for the
      // universal (web page) adapter which uses a simpler quality check.
      const contentLength = (
        message.payload.assistantText ?? message.payload.pageContent ?? ''
      ).trim().length;
      if (contentLength < 80) {
        return { ok: true, data: { status: 'denied' } };
      }

      const policies = await getCachedPolicies();
      if (isDomainDenied(message.payload.sourceUrl, policies)) {
        return { ok: true, data: { status: 'denied' } };
      }

      const captureEnabled = await getCaptureEnabled();
      if (!captureEnabled) {
        return { ok: true, data: { status: 'denied' } };
      }

      try {
        const result = await api.capture(message.payload);
        if (result.status === 'created') {
          showCaptureBadge();
          // ── Store document ID locally so the popup/sidepanel browse is instant
          await storeDocumentId(result.memoryId, message.payload);
        }
        // Clear any previous error on success
        await browser.storage.local.remove('shail_last_capture_error');
        return { ok: true, data: result };
      } catch (err) {
        showErrorBadge();
        const rawMsg    = (err as Error).message ?? '';
        const isOffline = rawMsg === 'BACKEND_OFFLINE' || rawMsg === 'BACKEND_TIMEOUT';
        const friendlyMsg =
          rawMsg === 'BACKEND_OFFLINE'
            ? 'SHAIL backend is offline — capture queued, will retry'
            : rawMsg === 'BACKEND_TIMEOUT'
            ? 'Backend timeout — capture queued, will retry'
            : rawMsg;
        // If the backend was unreachable, queue the capture for later drain.
        if (isOffline) {
          try {
            const { enqueue } = await import('../src/lib/offlineQueue');
            await enqueue(message.payload);
          } catch (qErr) {
            console.warn('[SHAIL] queue enqueue failed:', qErr);
          }
        }
        // Store the error so the Options page can surface it
        await browser.storage.local.set({
          shail_last_capture_error: {
            message: friendlyMsg,
            timestamp: new Date().toISOString(),
          },
        });
        if (isOffline) {
          // Treat queued captures as a soft success so the popup does not
          // flash a red error — they will drain when the backend comes back.
          return { ok: true, data: { status: 'denied' } };
        }
        return { ok: false, error: friendlyMsg };
      }
    }

    case 'SEARCH': {
      try {
        const bundle = await api.search(message.payload);
        return { ok: true, data: bundle };
      } catch (err) {
        return { ok: false, error: (err as Error).message };
      }
    }

    case 'OPEN_SIDEPANEL': {
      // Set focus flag synchronously before the open call
      browser.storage.local.set({ shail_focus_search: true });
      if (sender.tab?.id) {
        chrome.sidePanel.open({ tabId: sender.tab.id }).catch(() => {
          if (sender.tab?.windowId) {
            chrome.sidePanel.open({ windowId: sender.tab.windowId }).catch(() => {});
          }
        });
      } else {
        // Fallback: open on active window
        chrome.windows.getCurrent(w => {
          if (w?.id) chrome.sidePanel.open({ windowId: w.id }).catch(() => {});
        });
      }
      return { ok: true, data: null };
    }

    case 'GET_POLICIES': {
      const policies = await getCachedPolicies();
      return { ok: true, data: policies };
    }

    case 'FETCH_ASCENT': {
      try {
        const data = await api.getAscent(message.payload.id);
        return { ok: true, data };
      } catch (err) {
        return { ok: false, error: (err as Error).message };
      }
    }

    case 'TOGGLE_TODO': {
      try {
        const { ascentId, todoId, completed } = message.payload;
        const data = await api.toggleTodo(ascentId, todoId, completed);
        return { ok: true, data };
      } catch (err) {
        return { ok: false, error: (err as Error).message };
      }
    }

    default:
      return { ok: false, error: 'Unknown message type' };
  }
}

// ─── Background entry ─────────────────────────────────────────────────────────

export default defineBackground(() => {
  // Ensure side panel is enabled globally
  chrome.sidePanel.setOptions({ enabled: true });

  // Central message bus
  browser.runtime.onMessage.addListener(
    (message: unknown, sender, sendResponse) => {
      handleMessage(message as BackgroundMessage, sender)
        .then(sendResponse)
        .catch(err =>
          sendResponse({ ok: false, error: (err as Error).message })
        );
      return true; // keep channel open for async response
    }
  );

  // Open sidepanel when user clicks the extension icon
  browser.action.onClicked.addListener(async (tab) => {
    if (tab.id) {
      await browser.sidePanel.open({ tabId: tab.id });
    }
  });

  // Ctrl+Space (manifest command) → open side panel + signal search focus.
  // CRITICAL: Do NOT use async/await here — Chrome only propagates the user
  // gesture to synchronous code. Using await before sidePanel.open() silently
  // drops the call. Use .then() chains to stay in the gesture context.
  // ── Periodic offline-queue drain ────────────────────────────────────────
  // Every 30 s, ping the backend; if up, drain pending captures.
  const drainTick = async () => {
    try {
      const { pingBackend } = await import('../src/lib/api');
      const { drain, size } = await import('../src/lib/offlineQueue');
      const queued = await size();
      if (queued === 0) return;
      const health = await pingBackend();
      if (!health.ok) return;
      await drain(async (payload) => { await api.capture(payload); });
    } catch (err) {
      console.warn('[SHAIL] drain tick failed:', err);
    }
  };
  setInterval(drainTick, 30_000);
  // Kick once at startup so the badge clears fast after a restart
  setTimeout(drainTick, 3_000);

  browser.commands.onCommand.addListener((command) => {
    if (command === 'open-sidepanel') {
      // Signal sidepanel to auto-focus search (fire-and-forget)
      browser.storage.local.set({ shail_focus_search: true });

      // Open side panel — try tabId first, fall back to windowId
      browser.tabs.query({ active: true, currentWindow: true }).then(tabs => {
        const tab = tabs[0];
        if (!tab) return;

        if (tab.id) {
          chrome.sidePanel.open({ tabId: tab.id }).catch(() => {
            // tabId rejected (e.g. chrome:// page) — try window-level
            if (tab.windowId) {
              chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {});
            }
          });
        } else if (tab.windowId) {
          chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {});
        }
      });
    }
  });
});
