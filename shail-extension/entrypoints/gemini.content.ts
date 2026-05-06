import { buildAiCandidate, isCaptureAllowed, makeCaptureId, observeWithStability, sendCapture } from '../src/lib/capture';
import { extractTranscript } from '../src/lib/conversation-extractor';
import { scoreContent } from '../src/lib/importance';
import { showCapturePrompt } from '../src/lib/notify';

export default defineContentScript({
  matches: [
    'https://gemini.google.com/*',
    'https://bard.google.com/*',
  ],
  runAt: 'document_idle',

  main() {
    let lastSeenText     = '';
    let lastCapturedText = '';
    let stopObserver: (() => void) | null = null;

    const RESPONSE_SELECTORS = [
      'model-response .markdown',
      'model-response',
      '.model-response-text',
      '[class*="response-content"]',
      'ms-text-chunk',
    ];

    const QUERY_SELECTORS = [
      '.query-text',
      '.user-query-bubble-with-background',
      'query-text',
      '[class*="QueryText"]',
    ];

    function isStreaming(): boolean {
      return !!(
        document.querySelector('.loading-indicator') ||
        document.querySelector('[aria-label="Stop"]') ||
        document.querySelector('mat-progress-bar')
      );
    }

    async function tryCapture() {
      if (!await isCaptureAllowed(location.href)) return;
      if (isStreaming()) return;

      const transcript = extractTranscript({
        userSelectors: QUERY_SELECTORS,
        assistantSelectors: RESPONSE_SELECTORS,
        maxTurns: 10,
      });
      if (!transcript) return;

      if (!transcript.latestAssistantText || transcript.latestAssistantText === lastSeenText) return;
      lastSeenText = transcript.latestAssistantText;

      const { bucket } = scoreContent(transcript.latestAssistantText);
      if (bucket === 'skip') return;

      const assistantPayload = transcript.turnCount > 0
        ? transcript.assistantText
        : transcript.latestAssistantText;
      const userText = transcript.userText;

      async function doCapture() {
        if (transcript.latestAssistantText === lastCapturedText) return;
        lastCapturedText = transcript.latestAssistantText;
        const candidate = await buildAiCandidate({
          sourceApp: 'gemini',
          userText,
          assistantText: assistantPayload,
        });
        await sendCapture(candidate);
      }

      const cid = await makeCaptureId(location.href, assistantPayload);
      const stored = await browser.storage.local.get('shail_doc_index');
      const index = (stored['shail_doc_index'] as Array<{ customId?: string }>) ?? [];
      if (index.some(e => e.customId === cid)) return;

      showCapturePrompt({
        title:     userText || document.title,
        sourceApp: 'gemini',
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
