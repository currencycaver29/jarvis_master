const KEY_PREFIX = 'shail_session_buffer_';
const MAX_CHARS  = 50_000;

interface SessionBuffer {
  conversationId: string;
  transcript: string;
  charCount: number;
  lastUpdated: number;
}

function bufferKey(conversationId: string): string {
  return KEY_PREFIX + conversationId;
}

export async function getSessionBuffer(conversationId: string): Promise<SessionBuffer | null> {
  try {
    const result = await chrome.storage.session.get(bufferKey(conversationId));
    return (result[bufferKey(conversationId)] as SessionBuffer) ?? null;
  } catch {
    return null;
  }
}

/**
 * Persist the latest full transcript for a conversation.
 * Keeps whichever version is longer — handles the case where a page refresh
 * renders fewer DOM turns than the buffer already holds.
 * Trims from the start if the transcript exceeds MAX_CHARS.
 */
export async function appendToSessionBuffer(
  conversationId: string,
  newTranscript: string,
): Promise<SessionBuffer> {
  const existing = await getSessionBuffer(conversationId);

  let transcript = newTranscript.length > (existing?.transcript.length ?? 0)
    ? newTranscript
    : (existing?.transcript ?? newTranscript);

  if (transcript.length > MAX_CHARS) {
    // Trim from the front to preserve the most recent turns
    transcript = transcript.slice(transcript.length - MAX_CHARS);
    // Re-align to the first complete turn boundary
    const boundary = transcript.indexOf('\n\nUser:');
    if (boundary !== -1) transcript = transcript.slice(boundary + 2);
  }

  const buffer: SessionBuffer = {
    conversationId,
    transcript,
    charCount: transcript.length,
    lastUpdated: Date.now(),
  };

  try {
    await chrome.storage.session.set({ [bufferKey(conversationId)]: buffer });
  } catch {
    // Storage may be full or unavailable — proceed without persisting
  }

  return buffer;
}

export function buildFullTranscript(buffer: SessionBuffer): string {
  return buffer.transcript;
}
