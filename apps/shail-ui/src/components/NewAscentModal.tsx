import React, { useState } from 'react';
import { api, AscentDetail } from '../api';

interface Props {
  onClose: () => void;
  onCreated: (a: AscentDetail) => void;
}

export function NewAscentModal({ onClose, onCreated }: Props) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const a = await api.createAscent({ name: name.trim(), description: description.trim() });
      onCreated(a);
      onClose();
    } catch (e: unknown) {
      // The 402 free-tier-limit error comes through as a JSON-ish string.
      const msg = e instanceof Error ? e.message : String(e);
      // Try to surface the readable "message" inside the FastAPI 402 detail payload.
      let display = msg;
      try {
        const parsed = JSON.parse(msg);
        if (parsed?.detail?.message) display = parsed.detail.message;
        else if (parsed?.detail) display = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail);
      } catch { /* not JSON */ }
      setError(display || 'Failed to create ascent');
      setSubmitting(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.85)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 200,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 520,
          maxWidth: '92%',
          background: '#0d0d0d',
          border: '1px solid #1f1f1f',
          borderRadius: 12,
          padding: '32px 36px',
        }}
      >
        <div style={{ marginBottom: 6, fontSize: 11, color: '#666', fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace', letterSpacing: '0.08em' }}>
          NEW ASCENT
        </div>
        <h2 style={{ margin: '0 0 18px', fontSize: 18, fontWeight: 500, color: '#fff' }}>
          Define your goal
        </h2>

        <label style={{ display: 'block', fontSize: 11, color: '#666', marginBottom: 6, letterSpacing: '0.04em' }}>
          GOAL
        </label>
        <input
          autoFocus
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="Build an authentication subsystem"
          maxLength={120}
          style={{
            width: '100%',
            padding: '10px 12px',
            fontSize: 13,
            background: '#0a0a0a',
            border: '1px solid #1f1f1f',
            borderRadius: 6,
            color: '#fff',
            outline: 'none',
            marginBottom: 16,
          }}
        />

        <label style={{ display: 'block', fontSize: 11, color: '#666', marginBottom: 6, letterSpacing: '0.04em' }}>
          DETAILS  <span style={{ color: '#333' }}>(optional — gives Gemma more context)</span>
        </label>
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Add user signup with email + Google OAuth, persist sessions, support password reset…"
          rows={4}
          style={{
            width: '100%',
            padding: '10px 12px',
            fontSize: 13,
            background: '#0a0a0a',
            border: '1px solid #1f1f1f',
            borderRadius: 6,
            color: '#fff',
            outline: 'none',
            resize: 'vertical',
            fontFamily: 'inherit',
            marginBottom: 18,
          }}
        />

        <div style={{ fontSize: 11, color: '#666', lineHeight: 1.5, marginBottom: 24 }}>
          SHAIL will read your relevant memories and have your local model break this into deliverables
          and atomic todos. Generation typically takes 20–40 seconds.
        </div>

        {error && (
          <div style={{
            padding: '10px 12px',
            marginBottom: 14,
            border: '1px solid #3a1010',
            background: '#1a0808',
            borderRadius: 6,
            fontSize: 12,
            color: '#ef9a9a',
          }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            disabled={submitting}
            style={{
              padding: '8px 18px',
              fontSize: 12,
              background: 'transparent',
              border: '1px solid #1e1e1e',
              borderRadius: 6,
              color: '#666',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={submitting || !name.trim()}
            style={{
              padding: '8px 22px',
              fontSize: 12,
              background: submitting || !name.trim() ? '#222' : '#fff',
              color: submitting || !name.trim() ? '#555' : '#000',
              border: 'none',
              borderRadius: 6,
              fontWeight: 500,
              cursor: submitting || !name.trim() ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? 'Generating plan…' : 'Generate ascent'}
          </button>
        </div>
      </div>
    </div>
  );
}
