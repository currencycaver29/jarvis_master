import React from 'react';

const CONNECTORS = [
  { name: 'Google Drive', icon: '▲', desc: 'Sync documents and files from your Drive', ready: false },
  { name: 'Notion',       icon: '◻', desc: 'Import pages and databases from your workspace', ready: false },
  { name: 'GitHub',       icon: '◈', desc: 'Capture code, issues, and pull requests', ready: false },
];

export function Connections() {
  return (
    <div style={{ flex: 1, padding: '40px 48px', overflowY: 'auto' }}>
      <h1 style={{ margin: 0, fontSize: 22, fontWeight: 500, color: '#fff', letterSpacing: '-0.4px' }}>Connections</h1>
      <p style={{ margin: '6px 0 40px', fontSize: 13, color: '#3a3a3a' }}>Connect external data sources to your memory.</p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 560 }}>
        {CONNECTORS.map(c => (
          <div key={c.name} style={{ background: '#0a0a0a', border: '1px solid #161616', borderRadius: 10, padding: '20px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <span style={{ fontSize: 20, color: '#2a2a2a' }}>{c.icon}</span>
              <div>
                <div style={{ fontSize: 14, fontWeight: 500, color: '#ccc' }}>{c.name}</div>
                <div style={{ fontSize: 12, color: '#333', marginTop: 2 }}>{c.desc}</div>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 10, color: '#2a2a2a', background: '#111', border: '1px solid #1a1a1a', borderRadius: 4, padding: '3px 7px', letterSpacing: '0.06em', fontWeight: 600 }}>COMING SOON</span>
              <button disabled style={{ padding: '7px 16px', borderRadius: 6, fontSize: 12, fontWeight: 500, cursor: 'not-allowed', background: '#0d0d0d', border: '1px solid #1a1a1a', color: '#2a2a2a' }}>
                Connect
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
