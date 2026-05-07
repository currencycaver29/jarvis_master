import type { SourceApp } from '../types/contracts';

const PATTERNS: Partial<Record<SourceApp, RegExp>> = {
  chatgpt:    /\/c\/([a-z0-9-]+)/i,
  claude:     /\/chat\/([a-z0-9-]+)/i,
  gemini:     /\/app\/([a-z0-9-]+)/i,
};

/**
 * Extract the provider-specific conversation UUID from the current URL.
 * Returns null if no UUID is present (e.g. brand-new chat, root page).
 * When null, callers fall back to the legacy content-fingerprint customId.
 */
export function extractConversationId(url: string, sourceApp: SourceApp): string | null {
  const pattern = PATTERNS[sourceApp];
  if (!pattern) return null;
  try {
    const path = new URL(url).pathname;
    const match = path.match(pattern);
    return match?.[1] ?? null;
  } catch {
    return null;
  }
}
