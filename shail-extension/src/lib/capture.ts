import { sha256 } from './crypto';
import { isDomainDenied } from './utils';
import { appendToSessionBuffer, buildFullTranscript } from './session-buffer';
import type { CaptureCandidate, SitePolicy, SourceApp } from '../types/contracts';

// ─── Policy cache (30s TTL) ───────────────────────────────────────────────────

let _policyCache: SitePolicy[] | null = null;
let _policyCacheAt = 0;
const POLICY_TTL_MS = 30_000;

export async function isCaptureAllowed(url: string): Promise<boolean> {
  const now = Date.now();
  if (_policyCache === null || now - _policyCacheAt > POLICY_TTL_MS) {
    try {
      const stored = await browser.storage.local.get('shail_policies');
      _policyCache = (stored['shail_policies'] as SitePolicy[]) ?? [];
    } catch {
      _policyCache = [];
    }
    _policyCacheAt = now;
  }
  return !isDomainDenied(url, _policyCache);
}

/**
 * Builds a stable SHA-256 customId for deduplication.
 * Combines url + calendar date + a content fingerprint so the same page
 * visited twice on the same day produces the same ID.
 */
export async function makeCaptureId(
  url: string,
  contentFingerprint = '',
): Promise<string> {
  const date = new Date().toDateString(); // e.g. "Mon Apr 13 2026"
  return sha256(url + date + contentFingerprint.slice(0, 80));
}

/**
 * Sends a CaptureCandidate to the background service worker.
 * Silently drops the message if the extension context is invalidated
 * (e.g. user navigated away mid-capture).
 */
export async function sendCapture(candidate: CaptureCandidate): Promise<void> {
  try {
    await browser.runtime.sendMessage({ type: 'CAPTURE', payload: candidate });
  } catch {
    // Extension context invalidated or background not ready — ignore silently
  }
}

/**
 * Builds a CaptureCandidate for an AI conversation turn.
 *
 * When conversationId is supplied (Sprint 1+):
 *   - customId is stable across all captures of the same conversation
 *   - The session buffer accumulates the full transcript across page refreshes
 *   - Background dedup ring is bypassed (backend handles upsert idempotently)
 *
 * When conversationId is absent (non-conversation pages, unknown URL patterns):
 *   - Falls back to legacy content-fingerprint customId
 *   - No buffer involvement
 */
export async function buildAiCandidate(opts: {
  sourceApp: SourceApp;
  userText: string;
  assistantText: string;
  conversationId?: string;
}): Promise<CaptureCandidate> {
  const url = window.location.href;

  let customId: string;
  let finalAssistantText: string;

  if (opts.conversationId) {
    customId = await sha256('shail_session_' + opts.conversationId);
    const buffer = await appendToSessionBuffer(opts.conversationId, opts.assistantText);
    finalAssistantText = buildFullTranscript(buffer);
  } else {
    customId = await makeCaptureId(url, opts.assistantText);
    finalAssistantText = opts.assistantText;
  }

  return {
    customId,
    conversationId: opts.conversationId,
    eventType: 'ai_conversation',
    sourceApp: opts.sourceApp,
    sourceUrl: url,
    timestamp: new Date().toISOString(),
    title: document.title,
    userText: opts.userText,
    assistantText: finalAssistantText,
  };
}

/**
 * Debounced MutationObserver that fires `onStable` once DOM stops changing.
 * Returns a cleanup function.
 */
export function observeWithStability(
  root: Element | Document,
  onStable: () => void,
  stabilityMs = 500,
): () => void {
  let timer: ReturnType<typeof setTimeout> | null = null;

  const observer = new MutationObserver(() => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(onStable, stabilityMs);
  });

  observer.observe(root, {
    childList: true,
    subtree: true,
    characterData: true,
  });

  return () => {
    if (timer) clearTimeout(timer);
    observer.disconnect();
  };
}
