import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api';

interface Props {
  name: string;
  email: string;
  tier: 'free' | 'pro';
  onClose: () => void;
  onLogout: () => void;
  onNavigate: (to: string) => void;
}

const HELP_URL = 'https://docs.shailai.in';

export function AccountOverlay({ name, email, tier, onClose, onLogout, onNavigate }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [mergeCount, setMergeCount] = useState<number | null>(null);
  const [merging, setMerging] = useState(false);
  const [merged, setMerged] = useState(0);
  const [showUpgrade, setShowUpgrade] = useState(false);

  // Click-outside + Escape-to-close
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  // Feature C: pre-login memory sync row.
  // Show when: anonymous-count > 0 AND not previously dismissed for this user.
  useEffect(() => {
    const userId = localStorage.getItem('shail_user_id') || '';
    if (!userId) return;
    const dismissedKey = `shail_merge_shown_${userId}`;
    if (localStorage.getItem(dismissedKey) === 'true') return;
    api.anonymousCount()
      .then(d => { if (d.count > 0) setMergeCount(d.count); })
      .catch(() => { /* silent */ });
  }, []);

  const dismissMerge = () => {
    const userId = localStorage.getItem('shail_user_id') || '';
    if (userId) localStorage.setItem(`shail_merge_shown_${userId}`, 'true');
    setMergeCount(null);
  };

  const importMerge = async () => {
    setMerging(true);
    try {
      const r = await api.claimAnonymous();
      setMerged(r.claimed);
      // Mark dismissed so it doesn't reappear on next overlay open.
      const userId = localStorage.getItem('shail_user_id') || '';
      if (userId) localStorage.setItem(`shail_merge_shown_${userId}`, 'true');
      setTimeout(() => setMergeCount(null), 1500);
    } catch {
      setMerging(false);
    }
    setMerging(false);
  };

  const Row = ({ label, hint, onClick, danger = false }: { label: string; hint?: string; onClick: () => void; danger?: boolean }) => (
    <div
      onClick={onClick}
      style={{
        padding: '10px 14px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        cursor: 'pointer',
        fontSize: 13,
        color: danger ? '#ef4444' : '#ccc',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = '#171717')}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
    >
      <span>{label}</span>
      {hint && (
        <span style={{ fontSize: 11, color: '#444', fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace' }}>
          {hint}
        </span>
      )}
    </div>
  );

  const Divider = () => <div style={{ height: 1, background: '#161616', margin: '4px 0' }} />;

  return (
    <div
      ref={ref}
      style={{
        position: 'fixed',
        bottom: 70,
        left: 12,
        width: 264,
        background: '#0d0d0d',
        border: '1px solid #1f1f1f',
        borderRadius: 9,
        boxShadow: '0 12px 40px rgba(0,0,0,0.7)',
        zIndex: 50,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{ padding: '14px 14px 10px', borderBottom: '1px solid #161616' }}>
        <div style={{ fontSize: 12, color: '#fff', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {email || name}
        </div>
        <div style={{
          marginTop: 2,
          fontSize: 10,
          letterSpacing: '0.04em',
          color: '#666',
          fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
        }}>
          {tier.toUpperCase()} · LOCAL
        </div>
      </div>

      <div style={{ padding: '4px 0' }}>
        <Row label="Settings"     onClick={() => onNavigate('/settings')} />
        <Row label="Language"     hint="English ✓" onClick={() => { /* stub */ }} />
        <Row label="Get help"     onClick={() => window.open(HELP_URL, '_blank')} />
        <Row label="Upgrade plan" onClick={() => setShowUpgrade(true)} />
        <Row label="Learn more"   onClick={() => window.open(HELP_URL, '_blank')} />
      </div>

      <Divider />
      <Row label="Log out" onClick={onLogout} danger />

      {/* Pre-login memory sync (Feature C) */}
      {mergeCount !== null && (
        <>
          <Divider />
          <div style={{ padding: '12px 14px', background: '#0a0a0a' }}>
            {merged > 0 ? (
              <div style={{ fontSize: 12, color: '#22c55e' }}>
                ✓ {merged} {merged === 1 ? 'memory' : 'memories'} synced
              </div>
            ) : (
              <>
                <div style={{ fontSize: 12, color: '#999', marginBottom: 8, lineHeight: 1.45 }}>
                  {mergeCount} {mergeCount === 1 ? 'memory' : 'memories'} captured while logged out
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    disabled={merging}
                    onClick={importMerge}
                    style={{
                      flex: 1,
                      padding: '6px 0',
                      fontSize: 11,
                      background: '#fff',
                      color: '#000',
                      border: 'none',
                      borderRadius: 5,
                      cursor: merging ? 'wait' : 'pointer',
                      fontWeight: 500,
                      opacity: merging ? 0.6 : 1,
                    }}
                  >
                    {merging ? '…' : 'Sync to account'}
                  </button>
                  <button
                    onClick={dismissMerge}
                    disabled={merging}
                    style={{
                      flex: 1,
                      padding: '6px 0',
                      fontSize: 11,
                      background: 'transparent',
                      color: '#666',
                      border: '1px solid #1e1e1e',
                      borderRadius: 5,
                      cursor: 'pointer',
                    }}
                  >
                    Dismiss
                  </button>
                </div>
              </>
            )}
          </div>
        </>
      )}

      {/* Upgrade modal — overlays the overlay */}
      {showUpgrade && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.85)',
          zIndex: 200,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }} onClick={() => setShowUpgrade(false)}>
          <div onClick={e => e.stopPropagation()} style={{
            background: '#0d0d0d',
            border: '1px solid #1f1f1f',
            borderRadius: 12,
            padding: '32px 36px',
            maxWidth: 380,
            width: '90%',
          }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 500, color: '#fff' }}>Upgrade plan</h3>
            <p style={{ margin: '0 0 24px', fontSize: 13, color: '#999', lineHeight: 1.55 }}>
              Coming soon — Pro tier launches with unlimited ascents, 2,500 memory cap, and priority sync.
            </p>
            <button onClick={() => setShowUpgrade(false)} style={{
              padding: '8px 18px',
              fontSize: 12,
              background: '#1a1a1a',
              color: '#fff',
              border: '1px solid #1f1f1f',
              borderRadius: 6,
              cursor: 'pointer',
            }}>
              Got it
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
