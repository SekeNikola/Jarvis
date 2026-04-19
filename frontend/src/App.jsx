import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import VoiceOrb from './components/VoiceOrb';
import Transcript from './components/Transcript';
import StatusBar from './components/StatusBar';
import ContextPanel from './components/ContextPanel';
import SettingsPanel from './components/SettingsPanel';
import HolographicSpace from './components/HolographicSpace';
import HoloTaskDisplay from './components/HoloTaskDisplay';
import PersistentHolograms from './components/PersistentHolograms';

/* ── Styles ──────────────────────────────────────────────── */
const styles = {
  app: {
    width: '100vw',
    height: '100vh',
    background: 'radial-gradient(ellipse at center, #0f1923 0%, #0a0a0f 70%)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    overflow: 'hidden',
  },
  main: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    width: '100%',
    position: 'relative',
    zIndex: 1,
  },
  panelToggle: {
    position: 'absolute',
    top: 16,
    left: 16,
    background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 8,
    color: '#8899aa',
    padding: '8px 14px',
    cursor: 'pointer',
    fontSize: 13,
    fontFamily: 'monospace',
    transition: 'all 0.2s',
    zIndex: 10,
  },
  settingsToggle: {
    position: 'absolute',
    top: 16,
    right: 110,
    background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 8,
    color: '#8899aa',
    padding: '8px 14px',
    cursor: 'pointer',
    fontSize: 13,
    fontFamily: 'monospace',
    transition: 'all 0.2s',
    zIndex: 10,
  },
};

export default function App() {
  const {
    status, state, transcript, response, toolCalls,
    integrations, error, send, onTtsAudioRef, onStopTtsRef,
  } = useWebSocket('ws://localhost:8000/ws');

  const [panelOpen, setPanelOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [dismissedError, setDismissedError] = useState(null);

  // Auto-dismiss error after 8 seconds
  useEffect(() => {
    if (error && error !== dismissedError) {
      const t = setTimeout(() => setDismissedError(error), 8000);
      return () => clearTimeout(t);
    }
  }, [error, dismissedError]);

  /* ── Voice toggle ───────────────────────────────────── */
  // Stop any playing TTS audio (barge-in helper)
  const stopTtsPlayback = useCallback(() => {
    // Stop currently playing audio
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.onended = null;
      currentAudioRef.current.onerror = null;
      currentAudioRef.current = null;
    }
    // Clear queue
    audioQueueRef.current = [];
    isPlayingRef.current = false;
  }, []);

  const handleOrbClick = useCallback(() => {
    if (state === 'listening' || state === 'transcribing') {
      send({ type: 'stop_listening' });
    } else {
      // Barge-in: allow starting voice from ANY state (idle, speaking, responding, thinking)
      stopTtsPlayback();
      send({ type: 'start_listening' });
    }
  }, [state, send, stopTtsPlayback]);

  /* ── Double-tap Control shortcut for voice ─────────── */
  const lastCtrlRef = useRef(0);
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key !== 'Control') return;

      const now = Date.now();
      if (now - lastCtrlRef.current < 400) {
        // Double-tap detected — blur input so it doesn't steal focus
        lastCtrlRef.current = 0;
        document.activeElement?.blur();
        if (state === 'listening' || state === 'transcribing') {
          send({ type: 'stop_listening' });
        } else {
          // Barge-in: allow voice from any state
          stopTtsPlayback();
          send({ type: 'start_listening' });
        }
      } else {
        lastCtrlRef.current = now;
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [state, send]);

  /* ── Text input (Enter to send) ─────────────────────── */
  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && textInput.trim()) {
      // Barge-in: stop TTS if playing, then send
      stopTtsPlayback();
      send({ type: 'text_input', data: { text: textInput.trim() } });
      setTextInput('');
    }
  }, [textInput, send, stopTtsPlayback]);

  /* ── Audio playback ─────────────────────────────────── */
  const audioQueueRef = useRef([]);     // queue of complete MP3 blobs
  const isPlayingRef = useRef(false);
  const currentAudioRef = useRef(null); // the currently playing <audio>

  // Play next complete MP3 from queue
  const playNext = useCallback(() => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return;
    isPlayingRef.current = true;

    const blob = audioQueueRef.current.shift();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudioRef.current = audio;

    audio.onended = () => {
      URL.revokeObjectURL(url);
      currentAudioRef.current = null;
      isPlayingRef.current = false;
      playNext();
    };
    audio.onerror = (e) => {
      console.error('[JARVIS] Audio playback error:', e);
      URL.revokeObjectURL(url);
      currentAudioRef.current = null;
      isPlayingRef.current = false;
      playNext();
    };

    audio.play().catch((e) => {
      console.error('[JARVIS] Audio play() failed:', e);
      URL.revokeObjectURL(url);
      currentAudioRef.current = null;
      isPlayingRef.current = false;
      playNext();
    });
  }, []);

  // Wire up stop-TTS callback for barge-in
  useEffect(() => {
    onStopTtsRef.current = stopTtsPlayback;
    return () => { onStopTtsRef.current = null; };
  }, [stopTtsPlayback, onStopTtsRef]);

  // Wire up TTS audio callback — each message is one complete MP3
  useEffect(() => {
    onTtsAudioRef.current = (b64Audio) => {
      try {
        const binary = atob(b64Audio);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const blob = new Blob([bytes], { type: 'audio/mpeg' });
        audioQueueRef.current.push(blob);
        playNext();
      } catch (e) {
        console.error('[JARVIS] Audio decode error:', e);
      }
    };
    return () => { onTtsAudioRef.current = null; };
  }, [playNext, onTtsAudioRef]);

  return (
    <div style={styles.app}>
      {/* 3D Holographic background */}
      <HolographicSpace
        integrations={integrations}
        toolCalls={toolCalls}
        state={state}
      />

      {/* Holographic task panels — Iron Man style */}
      <HoloTaskDisplay toolCalls={toolCalls} state={state} />

      {/* Persistent Holograms (Reminders, Notes, Previous Tasks) */}
      <PersistentHolograms toolCalls={toolCalls} />

      {/* Status bar (top right — minimal) */}
      <StatusBar connectionStatus={status} />

      {/* Panel toggle */}
      <button
        style={styles.panelToggle}
        onClick={() => setPanelOpen(p => !p)}
        onMouseEnter={e => e.target.style.borderColor = 'rgba(0,150,255,0.4)'}
        onMouseLeave={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
      >
        {panelOpen ? '✕ Close' : '☰ History'}
      </button>

      {/* Settings toggle */}
      <button
        style={styles.settingsToggle}
        onClick={() => setSettingsOpen(p => !p)}
        onMouseEnter={e => e.target.style.borderColor = 'rgba(0,150,255,0.4)'}
        onMouseLeave={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
      >
        {settingsOpen ? '✕ Close' : '⚙ Settings'}
      </button>

      {/* Context panel (side left) */}
      <ContextPanel open={panelOpen} toolCalls={toolCalls} />

      {/* Settings panel (side right) */}
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} integrations={integrations} />

      {/* Main content — orb sits behind transcript */}
      <div style={styles.main}>
        <VoiceOrb
          state={state}
          onClick={handleOrbClick}
        />
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 3,
          pointerEvents: 'none',
        }}>
          <div style={{ pointerEvents: 'auto' }}>
            <Transcript
              state={state}
              transcript={transcript}
              response={response}
            />
          </div>
        </div>
      </div>

      {/* Error banner */}
      {error && error !== dismissedError && (
        <div style={{
          position: 'absolute',
          bottom: 80,
          left: '50%',
          transform: 'translateX(-50%)',
          width: '90%',
          maxWidth: 600,
          zIndex: 10,
          background: 'rgba(255,50,50,0.1)',
          border: '1px solid rgba(255,80,80,0.3)',
          borderRadius: 10,
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}>
          <span style={{ fontSize: 16 }}>⚠️</span>
          <span style={{
            flex: 1,
            fontFamily: 'monospace',
            fontSize: 12,
            color: '#ff8888',
            lineHeight: 1.4,
          }}>{error}</span>
          <button
            onClick={() => setDismissedError(error)}
            style={{
              background: 'none', border: 'none', color: '#ff6666',
              cursor: 'pointer', fontSize: 16, padding: '0 4px',
            }}
          >✕</button>
        </div>
      )}

      {/* Text input bar (bottom) */}
      <div style={{
        position: 'absolute',
        bottom: 24,
        left: '50%',
        transform: 'translateX(-50%)',
        width: '90%',
        maxWidth: 600,
        zIndex: 5,
      }}>
        <input
          type="text"
          placeholder={state === 'idle' ? 'Type a message… (double-tap ⌃ Control for voice)' : 'Type to interrupt…'}
          value={textInput}
          onChange={e => setTextInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={false}
          style={{
            width: '100%',
            padding: '14px 20px',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 12,
            color: '#c8d0d8',
            fontSize: 14,
            fontFamily: 'monospace',
            outline: 'none',
            transition: 'border-color 0.2s',
          }}
          onFocus={e => e.target.style.borderColor = 'rgba(0,150,255,0.3)'}
          onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.08)'}
        />
      </div>
    </div>
  );
}
