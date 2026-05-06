import { buildAiCandidate, isCaptureAllowed, makeCaptureId, observeWithStability, sendCapture } from '../src/lib/capture';
import { extractTranscript } from '../src/lib/conversation-extractor';
import { scoreContent } from '../src/lib/importance';
import { showCapturePrompt } from '../src/lib/notify';

export default defineContentScript({
  matches: ['https://claude.ai/*'],
  runAt: 'document_idle',

  main() {
    let lastSeenText     = '';
    let lastCapturedText = '';
    let stopObserver: (() => void) | null = null;

    const ASSISTANT_SELECTORS = [
      '.font-claude-message',
      '[data-testid="assistant-message"]',
      '.assistant-message',
      '[class*="AssistantMessage"]',
    ];

    const USER_SELECTORS = [
      '[data-testid="user-message"]',
      '.human-turn p',
      '[class*="HumanMessage"]',
      '[class*="UserMessage"]',
    ];

    function isStreaming(): boolean {
      return !!(
        document.querySelector('button[aria-label="Stop"]') ||
        document.querySelector('[data-is-streaming="true"]') ||
        document.querySelector('.streaming-indicator')
      );
    }

    async function tryCapture() {
      if (!await isCaptureAllowed(location.href)) return;
      if (isStreaming()) return;

      const transcript = extractTranscript({
        userSelectors: USER_SELECTORS,
        assistantSelectors: ASSISTANT_SELECTORS,
        maxTurns: 10,
      });
      if (!transcript) return;

      // Use latestAssistantText for change-detection (so we re-fire on each
      // new reply, not on irrelevant mutations of older turns).
      if (!transcript.latestAssistantText || transcript.latestAssistantText === lastSeenText) return;
      lastSeenText = transcript.latestAssistantText;

      // Score the latest reply only — historical turns don't gate capture.
      const { bucket } = scoreContent(transcript.latestAssistantText);
      if (bucket === 'skip') return;

      // assistantText sent to backend = full transcript (or single-turn fallback)
      const assistantPayload = transcript.turnCount > 0
        ? transcript.assistantText
        : transcript.latestAssistantText;
      const userText = transcript.userText;

      async function doCapture() {
        if (transcript.latestAssistantText === lastCapturedText) return;
        lastCapturedText = transcript.latestAssistantText;
        const candidate = await buildAiCandidate({
          sourceApp: 'claude',
          userText,
          assistantText: assistantPayload,
        });
        await sendCapture(candidate);
      }

      // Persistent dedup — fingerprint over the full transcript so adding
      // a new turn produces a new ID (and thus a new capture).
      const cid = await makeCaptureId(location.href, assistantPayload);
      const stored = await browser.storage.local.get('shail_doc_index');
      const index = (stored['shail_doc_index'] as Array<{ customId?: string }>) ?? [];
      if (index.some(e => e.customId === cid)) return;

      showCapturePrompt({
        title:     userText || document.title,
        sourceApp: 'claude',
        onSave:    doCapture,
        onSkip:    () => {},
      });
    }

    function attachObserver() {
      stopObserver?.();
      stopObserver = observeWithStability(document.body, tryCapture, 500);
    }

    attachObserver();

    let lastUrl = location.href;
    const navObserver = new MutationObserver(() => {
      if (location.href !== lastUrl) {
        lastUrl          = location.href;
        lastSeenText     = '';
        lastCapturedText = '';
        attachObserver();
      }
    });
    navObserver.observe(document.body, { childList: true, subtree: true });
  },
});
