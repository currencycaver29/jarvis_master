import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

const MONO = 'ui-monospace,"SF Mono",Menlo,monospace';

interface AnonItem { id: string; title: string; sourceApp: string; timestamp: string; }

interface Props {
  onDone: () => void;
}

export function AnonymousSyncModal({ onDone }: Props) {
  const [items, setItems]       = useState<AnonItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading]   = useState(true);
  const [syncing, setSyncing]   = useState(false);
  const [done, setDone]         = useState(false);
  const [claimed, setClaimed]   = useState(0);

  useEffect(() => {
    api.listAnonymousMemories()
      .then(r => {
        setItems(r.items);
        setSelected(new Set(r.items.map(i => i.id)));
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const toggleAll = () => {
    if (selected.size === items.length) setSelected(new Set());
    else setSelected(new Set(items.map(i => i.id)));
  };

  const toggle = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleSync = useCallback(async () => {
    if (!selected.size) return;
    setSyncing(true);
    try {
      const res = await api.claimAnonymous([...selected]);
      setClaimed(res.claimed);
      setDone(true);
    } catch {
      setSyncing(false);
    }
  }, [selected]);

  const timeAgo = (ts: string) => {
    const diff = Date.now() - new Date(ts).getTime();
    const d = Math.floor(diff / 86400000);
    if (d === 0) return 'today';
    if (d === 1) return 'yesterday';
    return `${d}d ago`;
  };

  const SOURCE_COLOR: Record<string, string> = {
    chatgpt: '#10a37f', claude: '#cc785c', gemini: '#4285f4',
    perplexity: '#20b2aa', web: '#6b7280',
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.82)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 9999,
    }}>
      <div style={{
        background: '#0a0a0a', border: '1px solid #1e1e1e', borderRadius: 12,
        width: 480, maxHeight: '80vh', display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{ padding: '24px 24px 20px', borderBottom: '1px solid #141414' }}>
          <div style={{ fontSize: 11, color: '#22c55e', fontFamily: MONO, letterSpacing: '0.08em', marginBottom: 8 }}>
            LOCAL MEMORIES FOUND
          </div>
          <h2 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 500, color: '#fff' }}>
            Sync pre-login memories?
          </h2>
          <p style={{ margin: 0, fontSize: 13, color: '#3a3a3a', lineHeight: 1.6 }}>
            {items.length} {items.length === 1 ? 'memory was' : 'memories were'} captured before you signed in.
            Sync them to your account — or skip and find them later in Settings.
          </p>
        </div>

        {done ? (
          <div style={{ padding: 32, textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>✓</div>
            <div style={{ fontSize: 15, color: '#fff', marginBottom: 6 }}>{claimed} {claimed === 1 ? 'memory' : 'memories'} synced</div>
            <div style={{ fontSize: 12, color: '#444', marginBottom: 24 }}>They're now in your account.</div>
            <button onClick={onDone} style={{ padding: '10px 28px', borderRadius: 7, fontSize: 13, background: '#fff', color: '#000', border: 'none', cursor: 'pointer', fontWeight: 600 }}>
              Done
            </button>
          </div>
        ) : (
          <>
            {/* Select all bar */}
            {!loading && items.length > 0 && (
              <div style={{ padding: '10px 24px', borderBottom: '1px solid #0f0f0f', display: 'flex', alignItems: 'center', gap: 10 }}>
                <input
                  type="checkbox"
                  checked={selected.size === items.length}
                  onChange={toggleAll}
                  style={{ accentColor: '#22c55e' }}
                />
                <span style={{ fontSize: 12, color: '#555' }}>
                  {selected.size === items.length ? 'Deselect all' : 'Select all'} ({items.length})
                </span>
              </div>
            )}

            {/* List */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
              {loading && (
                <div style={{ padding: '24px', fontSize: 12, color: '#333', textAlign: 'center' }}>Loading…</div>
              )}
              {!loading && items.length === 0 && (
                <div style={{ padding: '24px', fontSize: 12, color: '#333', textAlign: 'center' }}>No anonymous memories found.</div>
              )}
              {!loading && items.map(item => (
                <div
                  key={item.id}
                  onClick={() => toggle(item.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '10px 24px', cursor: 'pointer',
                    background: selected.has(item.id) ? '#0d0d0d' : 'transparent',
                    transition: 'background 0.1s',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(item.id)}
                    onChange={() => toggle(item.id)}
                    onClick={e => e.stopPropagation()}
                    style={{ accentColor: '#22c55e', flexShrink: 0 }}
                  />
                  <span style={{
                    fontSize: 10, fontWeight: 600, color: SOURCE_COLOR[item.sourceApp] ?? '#6b7280',
                    background: (SOURCE_COLOR[item.sourceApp] ?? '#6b7280') + '18',
                    border: `1px solid ${(SOURCE_COLOR[item.sourceApp] ?? '#6b7280')}30`,
                    borderRadius: 3, padding: '1px 5px', flexShrink: 0,
                  }}>
                    {item.sourceApp.toUpperCase()}
                  </span>
                  <span style={{ flex: 1, fontSize: 12, color: '#888', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.title || '(untitled)'}
                  </span>
                  <span style={{ fontSize: 11, color: '#2a2a2a', flexShrink: 0 }}>{timeAgo(item.timestamp)}</span>
                </div>
              ))}
            </div>

            {/* Footer */}
            <div style={{ padding: '16px 24px', borderTop: '1px solid #141414', display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button
                onClick={onDone}
                style={{ padding: '9px 20px', borderRadius: 7, fontSize: 13, background: 'none', border: '1px solid #1e1e1e', color: '#444', cursor: 'pointer' }}
              >
                Skip
              </button>
              <button
                onClick={handleSync}
                disabled={!selected.size || syncing}
                style={{
                  padding: '9px 20px', borderRadius: 7, fontSize: 13, fontWeight: 600,
                  background: selected.size ? '#fff' : '#111', color: selected.size ? '#000' : '#333',
                  border: 'none', cursor: selected.size ? 'pointer' : 'not-allowed',
                  opacity: syncing ? 0.6 : 1,
                }}
              >
                {syncing ? 'Syncing…' : `Sync ${selected.size} selected`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
