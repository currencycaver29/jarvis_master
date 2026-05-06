import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { clearAuth, getProfile } from '../auth';
import { AccountOverlay } from './AccountOverlay';

interface Props {
  collapsed: boolean;
}

export function AccountBar({ collapsed }: Props) {
  const [open, setOpen] = useState(false);
  const [profile, setProfile] = useState(getProfile());
  const [tier, setTier] = useState<'free' | 'pro'>('free');
  const navigate = useNavigate();

  useEffect(() => {
    const onAuth = () => setProfile(getProfile());
    window.addEventListener('shail-auth-updated', onAuth);
    window.addEventListener('storage', onAuth);
    return () => {
      window.removeEventListener('shail-auth-updated', onAuth);
      window.removeEventListener('storage', onAuth);
    };
  }, []);

  useEffect(() => {
    api.listAscents()
      .then(d => setTier(d.tier))
      .catch(() => { /* anon — fall through to 'free' */ });
  }, []);

  // Resolve display name: stored name → email local-part → "User"
  const name = profile.name || profile.email.split('@')[0] || 'User';
  const initial = (name[0] || 'U').toUpperCase();

  const handleLogout = () => {
    clearAuth();
    setOpen(false);
    navigate('/');
    // App.tsx listens to shail-auth-updated and will flip to AuthGate.
  };

  return (
    <>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          padding: collapsed ? '14px 0' : '12px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          cursor: 'pointer',
          borderTop: '1px solid #1a1a1a',
          background: open ? '#111' : 'transparent',
          transition: 'background 0.1s',
          justifyContent: collapsed ? 'center' : 'flex-start',
        }}
        title={collapsed ? name : undefined}
      >
        {/* Avatar */}
        <div style={{
          width: 28,
          height: 28,
          background: '#1a1a1a',
          borderRadius: 5,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 12,
          fontWeight: 600,
          color: '#fff',
          flexShrink: 0,
        }}>
          {initial}
        </div>
        {!collapsed && (
          <>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {name}
              </div>
              <div style={{
                fontSize: 10,
                color: '#444',
                fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
                letterSpacing: '0.03em',
              }}>
                {tier} · {tier === 'pro' ? 'summit' : 'base'}
              </div>
            </div>
            <span style={{ fontSize: 13, color: '#444', flexShrink: 0 }}>⚙</span>
          </>
        )}
      </div>

      {open && (
        <AccountOverlay
          name={name}
          email={profile.email}
          tier={tier}
          onClose={() => setOpen(false)}
          onLogout={handleLogout}
          onNavigate={(to) => { setOpen(false); navigate(to); }}
        />
      )}
    </>
  );
}
