import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api, MemoryRecord, SOURCE_COLOR, SOURCE_LABEL } from '../api';
import { MemoryCard } from '../components/MemoryCard';

const SOURCES = ['chatgpt', 'claude', 'gemini', 'perplexity', 'web'] as const;
const DATE_OPTS = [
  { key: 'all',   label: 'All time' },
  { key: 'today', label: 'Today' },
  { key: 'week',  label: 'This week' },
  { key: 'month', label: 'This month' },
] as const;

function dateAfter(key: string): string | undefined {
  if (key === 'all') return undefined;
  const d = new Date();
  if (key === 'today') { d.setHours(0,0,0,0); return d.toISOString(); }
  if (key === 'week')  { d.setDate(d.getDate()-7); return d.toISOString(); }
  if (key === 'month') { d.setDate(d.getDate()-30); return d.toISOString(); }
}

export function Memories() {
  const [records, setRecords]         = useState<MemoryRecord[]>([]);
  const [loading, setLoading]         = useState(true);
  const [query, setQuery]             = useState('');
  const [source, setSource]           = useState('all');
  const [date, setDate]               = useState('all');
  const [selected, setSelected]       = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [deleteModal, setDeleteModal] = useState<{ ids: string[]; label: string } | null>(null);
  const [blueprintIds, setBlueprintIds] = useState<Set<string>>(new Set());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchMemories = useCallback(async (q: string, src: string, dt: string) => {
    setLoading(true);
    try {
      const resp = await api.search({ query: q, k: 100, after: dateAfter(dt) });
      let items = resp.items;
      if (src !== 'all') items = items.filter(r => r.sourceApp === src);
      setRecords(items);
      // Batch-fetch which of these have blueprints so MemoryCard can render
      // the BLUEPRINT badge without one round-trip per card.
      if (items.length > 0) {
        try {
          const r = await api.getBlueprintIds(items.map(i => i.id));
          setBlueprintIds(new Set(r.ids));
        } catch { setBlueprintIds(new Set()); }
      } else {
        setBlueprintIds(new Set());
      }
    } catch { setRecords([]); setBlueprintIds(new Set()); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => fetchMemories(query, source, date), 300);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [query, source, date, fetchMemories]);

  function handleSelect(id: string, checked: boolean) {
    setSelected(prev => {
      const next = new Set(prev);
      checked ? next.add(id) : next.delete(id);
      return next;
    });
  }

  function handleSelectAll() {
    if (selected.size === records.length) setSelected(new Set());
    else setSelected(new Set(records.map(r => r.id)));
  }

  async function handleConfirmDelete(ids: string[]) {
    setBulkDeleting(true);
    await Promise.allSettled(ids.map(id => api.deleteMemory(id)));
    setRecords(prev => prev.filter(r => !ids.includes(r.id)));
    setSelected(prev => { const next = new Set(prev); ids.forEach(id => next.delete(id)); return next; });
    setBulkDeleting(false);
    setDeleteModal(null);
  }

  function handleBulkDelete() {
    if (!selected.size) return;
    const count = selected.size;
    setDeleteModal({ ids: [...selected], label: `Delete ${count} ${count === 1 ? 'memory' : 'memories'}? This cannot be undone.` });
  }

  function handleDeleted(id: string) {
    setRecords(prev => prev.filter(r => r.id !== id));
    setSelected(prev => { const next = new Set(prev); next.delete(id); return next; });
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: '40px 48px 0' }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 500, color: '#fff', letterSpacing: '-0.4px' }}>Memories</h1>
        <p style={{ margin: '6px 0 0', fontSize: 13, color: '#3a3a3a' }}>
          {loading ? 'Loading…' : `${records.length} ${records.length === 1 ? 'memory' : 'memories'}`}
        </p>
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 28 }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search memories…"
          style={{ background: '#0d0d0d', border: '1px solid #1a1a1a', borderRadius: 7, padding: '10px 14px', fontSize: 13, color: '#ccc', outline: 'none', width: '100%', boxSizing: 'border-box' }}
        />
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {/* Source pills */}
          {['all', ...SOURCES].map(s => {
            const isActive = source === s;
            const color = s === 'all' ? '#888' : (SOURCE_COLOR[s] ?? '#888');
            return (
              <button key={s} onClick={() => setSource(s)} style={{ padding: '5px 12px', borderRadius: 20, fontSize: 11, fontWeight: 500, cursor: 'pointer', border: `1px solid ${isActive ? color + '50' : '#1a1a1a'}`, background: isActive ? color + '18' : 'transparent', color: isActive ? color : '#444', transition: 'all 0.1s' }}>
                {s === 'all' ? 'All sources' : SOURCE_LABEL[s]}
              </button>
            );
          })}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {DATE_OPTS.map(opt => {
            const isActive = date === opt.key;
            return (
              <button key={opt.key} onClick={() => setDate(opt.key)} style={{ padding: '5px 12px', borderRadius: 20, fontSize: 11, fontWeight: 500, cursor: 'pointer', border: `1px solid ${isActive ? '#7c3aed50' : '#1a1a1a'}`, background: isActive ? '#7c3aed18' : 'transparent', color: isActive ? '#a78bfa' : '#444', transition: 'all 0.1s' }}>
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Bulk actions */}
      {records.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <button onClick={handleSelectAll} style={{ fontSize: 11, color: '#444', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
            {selected.size === records.length ? 'Deselect all' : 'Select all'}
          </button>
          {selected.size > 0 && (
            <button onClick={handleBulkDelete} disabled={bulkDeleting} style={{ fontSize: 11, color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', padding: 0, opacity: bulkDeleting ? 0.5 : 1 }}>
              {bulkDeleting ? 'Deleting…' : `Delete ${selected.size} selected`}
            </button>
          )}
        </div>
      )}

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', paddingBottom: 48, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {loading && records.length === 0 && (
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} style={{ height: 72, borderRadius: 8, background: '#0d0d0d', border: '1px solid #111', animation: 'pulse 1.5s ease-in-out infinite' }} />
          ))
        )}
        {!loading && records.length === 0 && (
          <div style={{ marginTop: 80, textAlign: 'center', color: '#252525', fontSize: 14 }}>No memories found</div>
        )}
        {records.map(r => (
          <MemoryCard
            key={r.id}
            record={r}
            selected={selected.has(r.id)}
            onSelect={handleSelect}
            onDeleted={handleDeleted}
            onDeleteRequest={(id) => setDeleteModal({ ids: [id], label: 'Delete this memory? This cannot be undone.' })}
            showCheckbox
            hasBlueprint={blueprintIds.has(r.id)}
          />
        ))}
      </div>

      {deleteModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ background: '#0d0d0d', border: '1px solid #1f1f1f', borderRadius: 12, padding: '32px 36px', maxWidth: 400, width: '90%' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 500, color: '#fff' }}>Delete memory?</h3>
            <p style={{ margin: '0 0 28px', fontSize: 13, color: '#555', lineHeight: 1.6 }}>{deleteModal.label}</p>
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={() => setDeleteModal(null)}
                style={{ flex: 1, padding: '9px 0', borderRadius: 7, fontSize: 13, cursor: 'pointer', background: 'transparent', border: '1px solid #1e1e1e', color: '#555' }}
              >
                Cancel
              </button>
              <button
                onClick={() => handleConfirmDelete(deleteModal.ids)}
                disabled={bulkDeleting}
                style={{ flex: 1, padding: '9px 0', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: '#ef4444', border: 'none', color: '#fff', opacity: bulkDeleting ? 0.6 : 1 }}
              >
                {bulkDeleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
