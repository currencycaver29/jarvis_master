import React, { useRef, useState } from 'react';
import { api } from '../api';
import { setApiKey, saveProfile } from '../auth';

interface Props { onAuth: () => void; }

export function AuthGate({ onAuth }: Props) {
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function handleGoogle() {
    setLoading(true);
    setError('');
    const state = crypto.randomUUID();
    const startUrl = api.googleStartUrl(state);
    window.open(startUrl, '_blank');

    let attempts = 0;
    pollRef.current = setInterval(async () => {
      attempts++;
      try {
        const result = await api.pollGoogleToken(state);
        if (result) {
          clearInterval(pollRef.current!);
          setApiKey(result.api_key, result.user_id);
          saveProfile(result.email, result.name);
          onAuth();
        } else if (attempts >= 30) {
          clearInterval(pollRef.current!);
          setLoading(false);
          setError('Sign-in timed out. Please try again.');
        }
      } catch (err) {
        clearInterval(pollRef.current!);
        setLoading(false);
        setError((err as Error).message ?? 'Sign-in failed');
      }
    }, 2000);
  }

  return (
    <div style={{ minHeight: '100vh', background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', maxWidth: 340 }}>
        <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.15em', color: '#222', textTransform: 'uppercase', marginBottom: 40 }}>
          SHAIL
        </div>
        <h1 style={{ margin: '0 0 10px', fontSize: 28, fontWeight: 400, color: '#fff', letterSpacing: '-0.6px' }}>Your memory.</h1>
        <p style={{ margin: '0 0 48px', fontSize: 14, color: '#333', lineHeight: 1.6 }}>Sign in to access your memories.</p>

        <button
          onClick={handleGoogle}
          disabled={loading}
          style={{
            width: '100%', padding: '13px 20px', borderRadius: 8, fontSize: 13, fontWeight: 500,
            cursor: loading ? 'default' : 'pointer', display: 'flex', alignItems: 'center',
            justifyContent: 'center', gap: 10, background: '#0d0d0d',
            border: '1px solid #1e1e1e', color: loading ? '#333' : '#bbb',
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => { if (!loading) { e.currentTarget.style.borderColor = '#2a2a2a'; e.currentTarget.style.color = '#fff'; }}}
          onMouseLeave={e => { e.currentTarget.style.borderColor = '#1e1e1e'; e.currentTarget.style.color = loading ? '#333' : '#bbb'; }}
        >
          {loading ? (
            <span style={{ fontSize: 12 }}>Waiting for Google…</span>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
              Continue with Google
            </>
          )}
        </button>

        {error && <p style={{ marginTop: 16, fontSize: 12, color: '#ef4444' }}>{error}</p>}
      </div>
    </div>
  );
}
