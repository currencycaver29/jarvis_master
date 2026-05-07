// ─── Capture ────────────────────────────────────────────────────────────────

export type EventType =
  | 'ai_conversation'
  | 'page_visit'
  | 'manual'
  | 'audio_clip'
  | 'video_clip'
  | 'pdf_doc'
  | 'mindmap'
  | 'diagram'
  | 'html_page'
  | 'document';

export type SourceApp =
  | 'chatgpt'
  | 'claude'
  | 'gemini'
  | 'perplexity'
  | 'web';

export interface CaptureCandidate {
  /** SHA-256 fingerprint — stable per conversation when conversationId is present */
  customId: string;
  /** Provider conversation UUID extracted from the URL (Sprint 1+) */
  conversationId?: string;
  eventType: EventType;
  sourceApp: SourceApp;
  sourceUrl: string;
  timestamp: string; // ISO 8601
  title?: string;
  userText?: string;      // the user's prompt (ai_conversation only)
  assistantText?: string; // the AI's response (ai_conversation only)
  pageContent?: string;   // trimmed page text (page_visit only)
}

// ─── Memory ─────────────────────────────────────────────────────────────────

export interface MemoryRecord {
  id: string;
  customId: string;
  eventType: EventType;
  sourceApp: SourceApp;
  sourceUrl: string;
  title: string;
  summary: string;
  timestamp: string;
  tags?: string[];
  pinned?: boolean;
  /** Relevance score from Supermemory's hybrid search (0–1). Higher = more relevant. */
  score?: number;
}

// ─── Search / Context ────────────────────────────────────────────────────────

export interface SearchFilters {
  sourceApp?: SourceApp;
  dateFrom?: string;
  dateTo?: string;
}

export interface SearchRequest {
  query: string;
  filters?: SearchFilters;
  scope?: 'all' | 'current_site';
  after?: string;  // ISO 8601 — only return memories with timestamp >= after
}

export interface ContextBundle {
  query: string;
  answer: string;
  items: MemoryRecord[];
  injectionText: string; // formatted block prefixed with "--- Prior context ---"
}

// ─── Guidance / Ghost Cursor ─────────────────────────────────────────────────

export interface DomCandidate {
  selector: string;
  label: string;
  rect: { x: number; y: number; width: number; height: number };
}

export interface GuidanceStep {
  order: number;
  instruction: string;
  why: string;
  target: {
    selector: string;
    fallbackBox: [number, number, number, number]; // x1, y1, x2, y2
    label: string;
  };
  confidence: number;
}

export interface GuidancePlan {
  steps: GuidanceStep[];
  audioRecommended: boolean;
}

export interface GuidanceRequest {
  query: string;
  domCandidates: DomCandidate[];
  screenshotRef: string; // base64
  currentUrl: string;
  appType: SourceApp | 'unknown';
  memoryContext?: string;
}

// ─── Site Policies ───────────────────────────────────────────────────────────

export type PolicyType = 'ALLOW' | 'SUMMARY_ONLY' | 'DENY';

export interface SitePolicy {
  domain: string;
  policy: PolicyType;
}

// ─── User / Auth ─────────────────────────────────────────────────────────────

export interface UserProfile {
  user_id: string;
  email:   string;
  name:    string;
}

// ─── API responses ────────────────────────────────────────────────────────────

export interface CaptureResult {
  memoryId: string;
  status: 'created' | 'duplicate' | 'denied';
  summary?: string;
}

export interface StatsResult {
  memoriesThisWeek: number;
  topSource: SourceApp | null;
  lastCaptured: MemoryRecord | null;
  recentCaptures: MemoryRecord[];
}

// ─── Background messages ─────────────────────────────────────────────────────

export type BackgroundMessage =
  | { type: 'CAPTURE'; payload: CaptureCandidate }
  | { type: 'SEARCH'; payload: SearchRequest }
  | { type: 'OPEN_SIDEPANEL' }
  | { type: 'GET_POLICIES' }
  | { type: 'FETCH_ASCENT'; payload: { id: string } }
  | { type: 'TOGGLE_TODO'; payload: { ascentId: string; todoId: string; completed: boolean } };

export type BackgroundResponse =
  | { ok: true; data: unknown }
  | { ok: false; error: string };
