import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, AscentDetail, HorizonItem } from '../api';

const MONO = 'ui-monospace, "SF Mono", Menlo, monospace';
const CARD = { background: '#0d0d0d', border: '1px solid #161616', borderRadius: 9 } as const;

interface ConfirmStartProps {
  item: HorizonItem;
  onCancel: () => void;
  onConfirm: (a: AscentDetail) => void;
}

function ConfirmStart({ item, onCancel, onConfirm }: ConfirmStartProps) {
  const [name, setName] = useState(item.suggested_name);
  const [description, setDescription] = useState(item.suggested_description);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const a = await api.createAscent({ name: name.trim(), description: description.trim() });
      onConfirm(a);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      let display = msg;
      try {
        const parsed = JSON.parse(msg);
        if (parsed?.detail?.message) display = parsed.detail.message;
      } catch { /* */ }
      setError(display);
      setBusy(false);
    }
  };

  return (
    <div onClick={onCancel} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: 520, maxWidth: '92%', background: '#0d0d0d',
        border: '1px solid #1f1f1f', borderRadius: 12, padding: '32px 36px',
      }}>
        <div style={{ fontSize: 11, color: '#666', fontFamily: MONO, letterSpacing: '0.08em', marginBottom: 4 }}>
          START ASCENT FROM HORIZON
        </div>
        <h2 style={{ margin: '0 0 18px', fontSize: 18, fontWeight: 500, color: '#fff' }}>{item.label}</h2>

        <label style={{ display: 'block', fontSize: 11, color: '#666', marginBottom: 6 }}>NAME</label>
        <input
          value={name} onChange={e => setName(e.target.value)}
          style={{
            width: '100%', padding: '10px 12px', fontSize: 13, background: '#0a0a0a',
            border: '1px solid #1f1f1f', borderRadius: 6, color: '#fff', outline: 'none', marginBottom: 16,
          }}
        />
        <label style={{ display: 'block', fontSize: 11, color: '#666', marginBottom: 6 }}>DETAILS</label>
        <textarea
          value={description} onChange={e => setDescription(e.target.value)}
          rows={4}
          style={{
            width: '100%', padding: '10px 12px', fontSize: 13, background: '#0a0a0a',
            border: '1px solid #1f1f1f', borderRadius: 6, color: '#fff', outline: 'none',
            resize: 'vertical', fontFamily: 'inherit', marginBottom: 18,
          }}
        />

        {error && (
          <div style={{ padding: '10px 12px', marginBottom: 14, border: '1px solid #3a1010', background: '#1a0808', borderRadius: 6, fontSize: 12, color: '#ef9a9a' }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button onClick={onCancel} disabled={busy} style={{
            padding: '8px 18px', fontSize: 12, background: 'transparent',
            border: '1px solid #1e1e1e', borderRadius: 6, color: '#666', cursor: 'pointer',
          }}>Cancel</button>
          <button onClick={submit} disabled={busy || !name.trim()} style={{
            padding: '8px 22px', fontSize: 12,
            background: busy || !name.trim() ? '#222' : '#fff',
            color: busy || !name.trim() ? '#555' : '#000',
            border: 'none', borderRadius: 6, fontWeight: 500,
            cursor: busy || !name.trim() ? 'not-allowed' : 'pointer',
          }}>{busy ? 'Generating…' : 'Generate plan'}</button>
        </div>
      </div>
    </div>
  );
}

export function Horizon() {
  const [items, setItems] = useState<HorizonItem[]>([]);
  const [confirming, setConfirming] = useState<HorizonItem | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await api.horizon();
      setItems(r.items);
    } catch { setItems([]); }
    setLoading(false);
  };

  useEffect(() => { refresh(); }, []);

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 40px' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 11, color: '#666', letterSpacing: '0.1em', fontFamily: MONO }}>HORIZON</div>
        <h1 style={{ margin: '6px 0 0', fontSize: 26, fontWeight: 500, color: '#fff' }}>Suggested goals</h1>
        <p style={{ margin: '6px 0 0', fontSize: 12, color: '#666', maxWidth: 640, lineHeight: 1.5 }}>
          Topics that recur across your memories but don't yet have an active ascent. Convert any of them
          into a real ascent — SHAIL will draft the plan with Gemma using the related memories as context.
        </p>
      </div>

      {loading && <div style={{ color: '#3a3a3a', fontSize: 12 }}>Detecting…</div>}

      {!loading && items.length === 0 && (
        <div style={{ ...CARD, padding: 40, textAlign: 'center' }}>
          <div style={{ fontSize: 14, color: '#666', marginBottom: 8 }}>No suggestions yet.</div>
          <div style={{ fontSize: 12, color: '#3a3a3a' }}>
            SHAIL surfaces a horizon item once a topic appears in 3+ memories without an active ascent.
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 14 }}>
        {items.map(it => (
          <div key={it.label} style={{ ...CARD, padding: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 9, color: '#fbbf24', letterSpacing: '0.1em', fontFamily: MONO }}>
                ◇ HORIZON
              </span>
              <span style={{ fontSize: 10, color: '#666', fontFamily: MONO }}>
                {it.memory_count} memories
              </span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 500, color: '#fff', marginBottom: 6 }}>
              {it.suggested_name}
            </div>
            <div style={{ fontSize: 11, color: '#888', lineHeight: 1.55, marginBottom: 14, minHeight: 50 }}>
              {it.suggested_description}
            </div>
            {it.sample_titles.length > 0 && (
              <div style={{ marginBottom: 14, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {it.sample_titles.slice(0, 2).map(t => (
                  <div key={t} style={{
                    fontSize: 10, color: '#444', fontFamily: MONO,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    · {t}
                  </div>
                ))}
              </div>
            )}
            <button
              onClick={() => setConfirming(it)}
              style={{
                width: '100%', padding: '8px 0', fontSize: 12,
                background: '#fff', color: '#000', border: 'none', borderRadius: 6,
                fontWeight: 500, cursor: 'pointer',
              }}
            >
              Start ascent
            </button>
          </div>
        ))}
      </div>

      {confirming && (
        <ConfirmStart
          item={confirming}
          onCancel={() => setConfirming(null)}
          onConfirm={(a) => { setConfirming(null); navigate('/ascents'); }}
        />
      )}
    </div>
  );
}
