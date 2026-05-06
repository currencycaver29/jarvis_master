import { buildAiCandidate, isCaptureAllowed, makeCaptureId, observeWithStability, sendCapture } from '../src/lib/capture';
import { extractTranscript } from '../src/lib/conversation-extractor';
import { scoreContent } from '../src/lib/importance';
import { showCapturePrompt } from '../src/lib/notify';

export default defineContentScript({
  matches: ['https://chat.openai.com/*', 'https://chatgpt.com/*'],
  runAt: 'document_idle',

  main() {
    let lastSeenText     = '';
    let lastCapturedText = '';
    let stopObserver: (() => void) | null = null;

    const ASSISTANT_SELECTORS = ["[data-message-author-role='assistant']"];
    const USER_SELECTORS      = ["[data-message-author-role='user']"];

    function isConversationPage(): boolean {
      return /^\/c\/[a-z0-9-]+/i.test(location.pathname);
    }

    async function tryCapture() {
      if (!await isCaptureAllowed(location.href)) return;
      if (!isConversationPage()) return;

      // Streaming guard — ChatGPT shows the Stop button while generating.
      const stopBtn = document.querySelector(
        'button[aria-label="Stop generating"], button[data-testid="stop-button"]',
      );
      if (stopBtn) return;

      const transcript = extractTranscript({
        userSelectors: USER_SELECTORS,
        assistantSelectors: ASSISTANT_SELECTORS,
        maxTurns: 10,
      });
      if (!transcript || !transcript.latestAssistantText) return;

      // Defend against the GPT picker / nav rendering as the "last assistant"
      // element on initial load — its first 200 chars contain raw markdown
      // link syntax that real replies almost never start with.
      if (/\]\(https?:\/\//.test(transcript.latestAssistantText.slice(0, 200))) return;

      if (transcript.latestAssistantText === lastSeenText) return;
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
          sourceApp: 'chatgpt',
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
        sourceApp: 'chatgpt',
        onSave:    doCapture,
        onSkip:    () => {},
      });
    }

    function attachObserver() {
      stopObserver?.();
      if (!isConversationPage()) return;
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
