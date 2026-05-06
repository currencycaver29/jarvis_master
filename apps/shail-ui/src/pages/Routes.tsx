import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, RouteCluster, MemoryRecord, SOURCE_LABEL, SOURCE_COLOR } from '../api';

const MONO = 'ui-monospace, "SF Mono", Menlo, monospace';
const CARD = { background: '#0d0d0d', border: '1px solid #161616', borderRadius: 9 } as const;

function timeAgo(ts: string): string {
  if (!ts) return '—';
  const t = new Date(ts).getTime();
  if (Number.isNaN(t)) return '—';
  const d = (Date.now() - t) / 1000;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

export function Routes() {
  const [routes, setRoutes] = useState<RouteCluster[]>([]);
  const [opened, setOpened] = useState<RouteCluster | null>(null);
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [loadingMemories, setLoadingMemories] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.routes().then(d => setRoutes(d.routes)).catch(() => setRoutes([]));
  }, []);

  const openRoute = async (r: RouteCluster) => {
    setOpened(r);
    setLoadingMemories(true);
    try {
      // Server-side filter: pull all and filter client-side because the
      // /search endpoint doesn't yet accept tag/cluster axis. Cheap for the
      // free-tier 500-cap corpus.
      const resp = await api.search({ query: '', k: 500 });
      const filtered = resp.items.filter(m => {
        if (r.axis === 'tag') return m.tags.some(t => t.toLowerCase() === r.label.toLowerCase());
        return m.sourceApp === r.label;
      });
      setMemories(filtered);
    } catch { setMemories([]); }
    setLoadingMemories(false);
  };

  if (opened) {
    return (
      <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px' }}>
        <button onClick={() => setOpened(null)} style={{
          background: 'none', border: 'none', color: '#666', fontSize: 12,
          padding: 0, cursor: 'pointer', marginBottom: 18, fontFamily: MONO,
        }}>← All routes</button>

        <div style={{ marginBottom: 22 }}>
          <div style={{ fontSize: 11, color: '#666', letterSpacing: '0.1em', fontFamily: MONO }}>
            ROUTE · {opened.axis.toUpperCase()}
          </div>
          <h1 style={{ margin: '6px 0 0', fontSize: 26, fontWeight: 500, color: '#fff' }}>{opened.label}</h1>
          <p style={{ margin: '6px 0 0', fontSize: 12, color: '#666' }}>
            {opened.count} {opened.count === 1 ? 'memory' : 'memories'} · last activity {timeAgo(opened.latest_ts)}
          </p>
        </div>

        {loadingMemories && <div style={{ color: '#3a3a3a', fontSize: 12 }}>Loading…</div>}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {memories.map(m => (
            <div key={m.id} style={{ ...CARD, padding: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                <span style={{
                  fontSize: 9, color: SOURCE_COLOR[m.sourceApp] || '#666',
                  fontFamily: MONO, letterSpacing: '0.08em',
                }}>
                  {(SOURCE_LABEL[m.sourceApp] || m.sourceApp).toUpperCase()}
                </span>
                <span style={{ fontSize: 10, color: '#3a3a3a', fontFamily: MONO }}>
                  {timeAgo(m.timestamp)}
                </span>
              </div>
              <div style={{ fontSize: 13, color: '#ccc', marginBottom: 4 }}>
                {m.title || m.sourceUrl}
              </div>
              <div style={{ fontSize: 11, color: '#555', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                {m.summary}
              </div>
            </div>
          ))}
          {!loadingMemories && memories.length === 0 && (
            <div style={{ color: '#3a3a3a', fontSize: 12 }}>No memories in this cluster.</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 11, color: '#666', letterSpacing: '0.1em', fontFamily: MONO }}>ROUTES</div>
        <h1 style={{ margin: '6px 0 0', fontSize: 26, fontWeight: 500, color: '#fff' }}>Auto-discovered clusters</h1>
        <p style={{ margin: '6px 0 0', fontSize: 12, color: '#666' }}>
          SHAIL groups your memories by recurring tags and sources. Read-only.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
        {routes.map(r => (
          <div key={r.label} onClick={() => openRoute(r)} style={{
            ...CARD, padding: 16, cursor: 'pointer',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={{
                fontSize: 9, color: '#666', letterSpacing: '0.1em', fontFamily: MONO,
              }}>
                {r.axis.toUpperCase()}
              </span>
              <span style={{ fontSize: 10, color: '#666', fontFamily: MONO }}>{r.count}</span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 500, color: '#fff', marginBottom: 8 }}>
              {r.label}
            </div>
            <div style={{ fontSize: 11, color: '#555', lineHeight: 1.5, minHeight: 40, overflow: 'hidden' }}>
              {r.sample_titles.length > 0
                ? r.sample_titles.slice(0, 2).join(' · ')
                : '(no titled memories)'}
            </div>
            <div style={{ marginTop: 10, fontSize: 10, color: '#3a3a3a', fontFamily: MONO }}>
              latest {timeAgo(r.latest_ts)}
            </div>
          </div>
        ))}
        {routes.length === 0 && (
          <div style={{ color: '#3a3a3a', fontSize: 12 }}>
            No clusters yet — capture a few memories to see SHAIL group them.
          </div>
        )}
      </div>
    </div>
  );
}
