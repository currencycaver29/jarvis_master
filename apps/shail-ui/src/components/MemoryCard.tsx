import React, { useState } from 'react';
import { Blueprint, MemoryRecord, SOURCE_COLOR, SOURCE_LABEL, api } from '../api';

interface Props {
  record: MemoryRecord;
  selected?: boolean;
  onSelect?: (id: string, checked: boolean) => void;
  onDeleted?: (id: string) => void;
  onDeleteRequest?: (id: string) => void;
  showCheckbox?: boolean;
  hasBlueprint?: boolean;
}

const MONO_F = 'ui-monospace,"SF Mono",Menlo,monospace';

export function MemoryCard({ record, selected, onSelect, onDeleted, onDeleteRequest, showCheckbox, hasBlueprint }: Props) {
  const [expanded, setExpanded]   = useState(false);
  const [content, setContent]     = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [deleting, setDeleting]   = useState(false);
  const [copied, setCopied]       = useState(false);
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const [bpStatus, setBpStatus]   = useState<'idle' | 'loading' | 'pending' | 'ready' | 'none'>('idle');

  const color = SOURCE_COLOR[record.sourceApp] ?? '#6b7280';
  const label = SOURCE_LABEL[record.sourceApp] ?? record.sourceApp;

  async function handleExpand() {
    if (expanded) { setExpanded(false); return; }
    setExpanded(true);
    if (content === null) {
      setLoadingContent(true);
      try {
        const full = await api.getMemory(record.id);
        setContent(full.content ?? full.summary ?? '');
      } catch {
        setContent(record.summary);
      } finally {
        setLoadingContent(false);
      }
    }
    if (bpStatus === 'idle') {
      setBpStatus('loading');
      try {
        const bp = await api.getBlueprint(record.id);
        setBlueprint(bp);
        setBpStatus('ready');
      } catch (err) {
        // 404 means extraction is still running (or content was too thin).
        // Mark pending so the UI can offer a retry without spamming.
        const msg = (err as Error).message || '';
        setBpStatus(msg.includes('404') ? 'pending' : 'none');
      }
    }
  }

  async function refreshBlueprint() {
    setBpStatus('loading');
    try {
      const bp = await api.getBlueprint(record.id);
      setBlueprint(bp);
      setBpStatus('ready');
    } catch {
      setBpStatus('pending');
    }
  }

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    if (deleting) return;
    if (onDeleteRequest) {
      onDeleteRequest(record.id);
      return;
    }
    setDeleting(true);
    try {
      await api.deleteMemory(record.id);
      onDeleted?.(record.id);
    } catch {
      setDeleting(false);
    }
  }

  const ts = new Date(record.timestamp);
  const timeStr = ts.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });

  return (
    <div
      style={{
        background: selected ? '#0f0f0f' : '#0a0a0a',
        border: `1px solid ${selected ? '#2a2a2a' : '#161616'}`,
        borderRadius: 8,
        padding: '16px 18px',
        cursor: 'pointer',
        transition: 'border-color 0.1s',
      }}
      onClick={handleExpand}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        {showCheckbox && (
          <input
            type="checkbox"
            checked={!!selected}
            onChange={e => { e.stopPropagation(); onSelect?.(record.id, e.target.checked); }}
            onClick={e => e.stopPropagation()}
            style={{ marginTop: 2, accentColor: '#ef4444', flexShrink: 0 }}
          />
        )}

        {/* Source chip */}
        <span style={{
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: '0.04em',
          color,
          background: color + '18',
          border: `1px solid ${color}30`,
          borderRadius: 4,
          padding: '2px 6px',
          flexShrink: 0,
          marginTop: 1,
        }}>
          {label}
        </span>

        {/* Blueprint badge — visible only when extraction has produced a row */}
        {hasBlueprint && (
          <span
            title="Structured blueprint extracted from this memory"
            style={{
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: '0.08em',
              color: '#8ab4f8',
              background: '#0c1424',
              border: '1px solid #1a2c4a',
              borderRadius: 4,
              padding: '2px 6px',
              flexShrink: 0,
              marginTop: 1,
              fontFamily: MONO_F,
            }}
          >
            BLUEPRINT
          </span>
        )}

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 500, color: '#e8e8e8', lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
              {record.title || record.sourceUrl}
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              <span style={{ fontSize: 11, color: '#3a3a3a' }}>{timeStr}</span>
              <button
                onClick={handleDelete}
                disabled={deleting}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2a2a2a', fontSize: 13, padding: '0 2px', lineHeight: 1, transition: 'color 0.1s' }}
                onMouseEnter={e => (e.currentTarget.style.color = '#ef4444')}
                onMouseLeave={e => (e.currentTarget.style.color = '#2a2a2a')}
                title="Delete"
              >
                {deleting ? '…' : '×'}
              </button>
            </div>
          </div>

          {!expanded && (
            <p style={{ margin: '6px 0 0', fontSize: 12, color: '#444', lineHeight: 1.55, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
              {record.summary}
            </p>
          )}
        </div>
      </div>

      {/* Tags */}
      {record.tags?.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10, paddingLeft: showCheckbox ? 26 : 0 }}>
          {record.tags.map(t => (
            <span key={t} style={{ fontSize: 10, color: '#333', background: '#141414', border: '1px solid #1e1e1e', borderRadius: 3, padding: '1px 6px' }}>
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Expanded content */}
      {expanded && (
        <div style={{ marginTop: 14, paddingLeft: showCheckbox ? 26 : 0 }} onClick={e => e.stopPropagation()}>
          {loadingContent ? (
            <div style={{ color: '#2a2a2a', fontSize: 12 }}>Loading…</div>
          ) : (
            <pre style={{ margin: 0, fontSize: 12, color: '#555', lineHeight: 1.65, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 320, overflowY: 'auto', fontFamily: 'inherit' }}>
              {content}
            </pre>
          )}

          {/* Blueprint — structured knowledge atoms */}
          <BlueprintPanel
            blueprint={blueprint}
            status={bpStatus}
            onRetry={refreshBlueprint}
          />

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
            <a
              href={record.sourceUrl}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: 11, color: '#333', textDecoration: 'none', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              onMouseEnter={e => (e.currentTarget.style.color = '#fff')}
              onMouseLeave={e => (e.currentTarget.style.color = '#333')}
            >
              {record.sourceUrl} ↗
            </a>
            <button
              onClick={() => {
                const text = content || record.summary || record.title || '';
                navigator.clipboard.writeText(text);
                setCopied(true);
                setTimeout(() => setCopied(false), 1600);
              }}
              style={{
                padding: '4px 12px', fontSize: 11, borderRadius: 5, cursor: 'pointer',
                background: 'none', border: '1px solid #1e1e1e', flexShrink: 0,
                color: copied ? '#22c55e' : '#333', fontFamily: MONO_F,
                transition: 'color 0.1s',
              }}
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


// ── Blueprint panel ──────────────────────────────────────────────────────────

function BlueprintPanel({
  blueprint, status, onRetry,
}: {
  blueprint: Blueprint | null;
  status: 'idle' | 'loading' | 'pending' | 'ready' | 'none';
  onRetry: () => void;
}) {
  if (status === 'idle' || status === 'none') return null;

  const HEADER = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14, marginBottom: 6 }}>
      <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', color: '#666', fontFamily: MONO_F }}>
        BLUEPRINT
      </span>
      <span style={{ flex: 1, height: 1, background: '#161616' }} />
      {status === 'pending' && (
        <button
          onClick={onRetry}
          style={{ fontSize: 10, color: '#666', background: 'none', border: '1px solid #1e1e1e', borderRadius: 4, padding: '2px 8px', cursor: 'pointer', fontFamily: MONO_F }}
        >
          retry
        </button>
      )}
    </div>
  );

  if (status === 'loading') {
    return (
      <>
        {HEADER}
        <div style={{ fontSize: 11, color: '#2a2a2a' }}>Reading…</div>
      </>
    );
  }
  if (status === 'pending') {
    return (
      <>
        {HEADER}
        <div style={{ fontSize: 11, color: '#444', lineHeight: 1.5 }}>
          Still extracting — blueprints generate in the background after capture.
          Tap retry in a moment.
        </div>
      </>
    );
  }
  if (!blueprint) return null;

  const sections: { label: string; items: string[]; tone: string }[] = [
    { label: 'Decisions',     items: blueprint.decisions,     tone: '#8ab4f8' },
    { label: 'Open questions', items: blueprint.open_questions, tone: '#f59e0b' },
    { label: 'Next actions',  items: blueprint.next_actions,  tone: '#22c55e' },
  ];

  return (
    <>
      {HEADER}
      {blueprint.summary && (
        <div style={{ fontSize: 12, color: '#888', lineHeight: 1.55, marginBottom: 10 }}>
          {blueprint.summary}
        </div>
      )}
      {sections.map(s => s.items.length > 0 && (
        <div key={s.label} style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, color: s.tone, fontFamily: MONO_F, letterSpacing: '0.06em', marginBottom: 4 }}>
            {s.label.toUpperCase()}
          </div>
          {s.items.map((item, i) => (
            <div key={i} style={{ fontSize: 12, color: '#aaa', lineHeight: 1.55, marginBottom: 2, paddingLeft: 10, position: 'relative' }}>
              <span style={{ position: 'absolute', left: 0, color: s.tone }}>·</span>
              {item}
            </div>
          ))}
        </div>
      ))}
      {blueprint.questions_answered.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, color: '#666', fontFamily: MONO_F, letterSpacing: '0.06em', marginBottom: 4 }}>
            Q&amp;A
          </div>
          {blueprint.questions_answered.map((qa, i) => (
            <div key={i} style={{ fontSize: 12, color: '#888', lineHeight: 1.55, marginBottom: 6, paddingLeft: 10 }}>
              <span style={{ color: '#ccc' }}>Q.</span> {qa.q}
              {qa.a && <><br/><span style={{ color: '#666' }}>A.</span> {qa.a}</>}
            </div>
          ))}
        </div>
      )}
      {blueprint.key_entities.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 4 }}>
          {blueprint.key_entities.map(e => (
            <span key={e} style={{ fontSize: 10, color: '#888', background: '#0f0f0f', border: '1px solid #1f1f1f', borderRadius: 4, padding: '2px 8px', fontFamily: MONO_F }}>
              {e}
            </span>
          ))}
        </div>
      )}
    </>
  );
}
