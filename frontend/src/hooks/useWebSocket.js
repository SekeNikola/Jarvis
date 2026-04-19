import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * JARVIS WebSocket hook.
 *
 * Manages the connection to the FastAPI backend and
 * exposes reactive state for the entire UI.
 */
export function useWebSocket(url) {
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const idRef = useRef(0); // generation counter — ignore stale sockets

  // Connection status
  const [status, setStatus] = useState('disconnected'); // disconnected | connecting | connected

  // App state machine
  const [state, setState] = useState('idle');
  // idle → listening → transcribing → thinking → speaking → idle

  // Data
  const [transcript, setTranscript] = useState('');    // last STT result
  const [response, setResponse] = useState('');        // Gemini's response (streamed)
  const [toolCalls, setToolCalls] = useState([]);      // {tool, input, result}
  const [integrations, setIntegrations] = useState({}); // from STATUS message
  const [error, setError] = useState(null);

  // TTS audio callback — set by App.jsx
  const onTtsAudioRef = useRef(null);
  // Stop TTS playback callback — set by App.jsx for barge-in
  const onStopTtsRef = useRef(null);

  /* ── Send message ─────────────────────────────────── */
  const send = useCallback((msg) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  /* ── Connect ──────────────────────────────────────── */
  const connect = useCallback(() => {
    // Bump generation — any events from older sockets will be ignored
    const myId = ++idRef.current;

    // Close any leftover socket
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      // Only close if OPEN — avoid browser warning on CONNECTING sockets
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }

    setStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (myId !== idRef.current) return; // stale
      setStatus('connected');
      setError(null);
      console.log('[JARVIS] Connected');
    };

    ws.onclose = () => {
      if (myId !== idRef.current) return; // stale — stay quiet
      setStatus('disconnected');
      setState('idle');
      console.log('[JARVIS] Disconnected — reconnecting in 3s');
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      if (myId !== idRef.current) return; // stale — stay quiet
      console.error('[JARVIS] WebSocket error');
      setError('Connection error');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch (e) {
        console.error('[JARVIS] Bad message', e);
      }
    };
  }, [url]);

  /* ── Message handler ──────────────────────────────── */
  const handleMessage = useCallback((msg) => {
    const { type, data } = msg;

    switch (type) {
      case 'status':
        setIntegrations(data.integrations || {});
        break;

      case 'listening':
        setState(data.active ? 'listening' : 'idle');
        if (data.active) {
          setTranscript('');
          setResponse('');
          setToolCalls([]);
        }
        break;

      case 'transcribing':
        setState('transcribing');
        break;

      case 'transcript':
        setTranscript(data.text || '');
        if (data.empty) setState('idle');
        break;

      case 'thinking':
        setState('thinking');
        setResponse('');
        // Don't clear toolCalls here — multi-step tool loops need to keep previous calls visible
        break;

      case 'tool_call':
        setToolCalls(prev => [...prev, {
          tool: data.tool,
          input: data.input,
          result: null,
          ts: Date.now(),
        }]);
        break;

      case 'tool_result':
        setToolCalls(prev => {
          const updated = [...prev];
          // Find the last matching tool without a result
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].tool === data.tool && !updated[i].result) {
              updated[i] = { ...updated[i], result: data.summary };
              break;
            }
          }
          return updated;
        });
        break;

      case 'browser_step':
        // Update the browser_agent tool call with step progress
        setToolCalls(prev => {
          const updated = [...prev];
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].tool === 'browser_agent') {
              updated[i] = {
                ...updated[i],
                browserStep: data.step,
                browserSummary: data.summary,
                browserUrl: data.url,
              };
              break;
            }
          }
          return updated;
        });
        break;

      case 'response_text':
        setState('responding');
        setResponse(prev => prev + (data.chunk || ''));
        break;

      case 'response_done':
        if (data.text) setResponse(data.text);
        if (!data.cancelled) setState('idle'); // will become 'speaking' if TTS follows
        else setState('idle');
        break;

      case 'speaking':
        if (data.active) setState('speaking');
        break;

      case 'tts_audio':
        if (onTtsAudioRef.current && data.audio) {
          onTtsAudioRef.current(data.audio);
        }
        break;

      case 'tts_done':
        setState('idle');
        break;

      case 'stop_tts':
        // Barge-in: backend says stop playback (user started speaking)
        // Audio cleanup is handled by App.jsx via stopTtsPlayback
        break;

      case 'error':
        setError(data.message);
        setState('idle');
        break;

      default:
        console.log('[JARVIS] Unknown message type:', type);
    }
  }, []);

  /* ── Lifecycle ────────────────────────────────────── */
  useEffect(() => {
    connect();
    return () => {
      // Bump generation so the closing socket's events are ignored
      idRef.current++;
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        const ws = wsRef.current;
        ws.onopen = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.onmessage = null;
        // Only close if already OPEN; if still CONNECTING, let it
        // die on its own — calling close() in CONNECTING state
        // triggers the browser's "closed before established" warning.
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {
    status,
    state,
    transcript,
    response,
    toolCalls,
    integrations,
    error,
    send,
    onTtsAudioRef,
    onStopTtsRef,
  };
}
