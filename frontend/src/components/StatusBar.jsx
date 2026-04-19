import React from 'react';

/**
 * StatusBar — minimal top-right status.
 * Only shows ONLINE/OFFLINE connection indicator.
 * All integration details moved to Settings panel.
 */

export default function StatusBar({ connectionStatus }) {
  return (
    <div style={{
      position: 'absolute', top: 16, right: 16,
      display: 'flex', alignItems: 'center', gap: 10,
      zIndex: 10,
    }}>
      <div style={{
        padding: '5px 14px', borderRadius: 20, fontSize: 10,
        fontFamily: 'monospace', letterSpacing: 1.2, textTransform: 'uppercase',
        background: connectionStatus === 'connected' ? 'rgba(0,230,118,0.06)' : 'rgba(255,80,80,0.06)',
        border: `1px solid ${connectionStatus === 'connected' ? 'rgba(0,230,118,0.15)' : 'rgba(255,80,80,0.15)'}`,
        color: connectionStatus === 'connected' ? '#55cc99' : '#ff6666',
      }}>
        {connectionStatus === 'connected' ? '● online' : '○ offline'}
      </div>
    </div>
  );
}
