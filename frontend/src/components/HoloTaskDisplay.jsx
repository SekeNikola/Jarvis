import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * HoloTaskDisplay — Iron Man-style holographic panels that appear
 * when JARVIS is working on tasks.
 *
 * Each active tool call gets a floating transparent-blue holographic
 * representation with an SVG icon and a label underneath.
 * Panels fade in from the sides, float/bob gently, and fade out
 * when the tool result arrives.
 */

/* ── Tool → hologram mapping ─────────────────────────────── */
const TOOL_HOLOGRAMS = {
  get_weather: {
    label: 'Weather',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        {/* Sun */}
        <circle cx="28" cy="24" r="8" />
        <line x1="28" y1="10" x2="28" y2="14" />
        <line x1="28" y1="34" x2="28" y2="38" />
        <line x1="14" y1="24" x2="18" y2="24" />
        <line x1="38" y1="24" x2="42" y2="24" />
        <line x1="18.1" y1="14.1" x2="21.2" y2="17.2" />
        <line x1="34.8" y1="30.8" x2="37.9" y2="33.9" />
        <line x1="37.9" y1="14.1" x2="34.8" y2="17.2" />
        {/* Cloud */}
        <path d="M22 42c-4 0-7-3-7-6.5S18 29 22 29c1-4 4-7 8.5-7s8 3.5 8.5 7.5c3 .5 5 3 5 5.5 0 3.5-3 6.5-7 6.5H22z" />
      </svg>
    ),
  },
  web_search: {
    label: 'Searching',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="28" cy="28" r="14" />
        <line x1="38" y1="38" x2="52" y2="52" strokeWidth="2.5" strokeLinecap="round" />
        <circle cx="28" cy="28" r="6" opacity="0.4" />
      </svg>
    ),
  },
  browser_agent: {
    label: 'Browsing',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="8" y="12" width="48" height="36" rx="4" />
        <line x1="8" y1="22" x2="56" y2="22" />
        <circle cx="15" cy="17" r="1.5" fill="currentColor" />
        <circle cx="21" cy="17" r="1.5" fill="currentColor" />
        <circle cx="27" cy="17" r="1.5" fill="currentColor" />
        <rect x="14" y="28" width="36" height="4" rx="2" opacity="0.4" />
        <rect x="14" y="36" width="24" height="4" rx="2" opacity="0.3" />
      </svg>
    ),
  },
  take_screenshot: {
    label: 'Screenshot',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="10" y="14" width="44" height="32" rx="4" />
        <circle cx="32" cy="30" r="8" />
        <circle cx="32" cy="30" r="3" />
        <rect x="24" y="14" width="16" height="6" rx="2" opacity="0.4" />
      </svg>
    ),
  },
  run_terminal_command: {
    label: 'Terminal',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="8" y="10" width="48" height="40" rx="4" />
        <polyline points="16,28 24,22 16,16" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
        <line x1="28" y1="28" x2="42" y2="28" strokeLinecap="round" />
        <rect x="16" y="34" width="20" height="2" rx="1" opacity="0.3" />
        <rect x="16" y="40" width="12" height="2" rx="1" opacity="0.2" />
      </svg>
    ),
  },
  read_file: {
    label: 'Reading File',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M16 8h22l12 12v36H16V8z" />
        <polyline points="38,8 38,20 50,20" />
        <line x1="22" y1="28" x2="44" y2="28" opacity="0.5" />
        <line x1="22" y1="34" x2="40" y2="34" opacity="0.4" />
        <line x1="22" y1="40" x2="36" y2="40" opacity="0.3" />
      </svg>
    ),
  },
  list_directory: {
    label: 'Files',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M8 16h18l4 6h26v30H8V16z" />
        <line x1="16" y1="32" x2="48" y2="32" opacity="0.3" />
        <line x1="16" y1="38" x2="44" y2="38" opacity="0.25" />
      </svg>
    ),
  },
  create_note: {
    label: 'Note',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="12" y="8" width="40" height="48" rx="3" />
        <line x1="20" y1="18" x2="44" y2="18" opacity="0.5" />
        <line x1="20" y1="24" x2="40" y2="24" opacity="0.4" />
        <line x1="20" y1="30" x2="36" y2="30" opacity="0.3" />
        <path d="M40 36l8-8 4 4-8 8H40v-4z" strokeWidth="1.5" />
      </svg>
    ),
  },
  send_telegram_message: {
    label: 'Telegram',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M8 32L56 12 44 52 32 38 44 24" />
        <line x1="32" y1="38" x2="32" y2="52" />
      </svg>
    ),
  },
  set_reminder: {
    label: 'Reminder',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="32" cy="32" r="18" />
        <polyline points="32,20 32,32 42,38" strokeWidth="2" strokeLinecap="round" />
        <path d="M18 8l-6 6M46 8l6 6" strokeWidth="2" />
        <line x1="32" y1="50" x2="32" y2="56" />
        <line x1="26" y1="55" x2="38" y2="55" strokeLinecap="round" />
      </svg>
    ),
  },
  control_app: {
    label: 'App Control',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="8" y="8" width="20" height="20" rx="4" />
        <rect x="36" y="8" width="20" height="20" rx="4" />
        <rect x="8" y="36" width="20" height="20" rx="4" />
        <rect x="36" y="36" width="20" height="20" rx="4" />
      </svg>
    ),
  },
  type_text: {
    label: 'Typing',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="6" y="20" width="52" height="28" rx="4" />
        <rect x="12" y="26" width="6" height="6" rx="1" opacity="0.4" />
        <rect x="22" y="26" width="6" height="6" rx="1" opacity="0.4" />
        <rect x="32" y="26" width="6" height="6" rx="1" opacity="0.4" />
        <rect x="42" y="26" width="6" height="6" rx="1" opacity="0.4" />
        <rect x="18" y="36" width="28" height="6" rx="1" opacity="0.3" />
      </svg>
    ),
  },
  press_key: {
    label: 'Key Press',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="16" y="16" width="32" height="32" rx="6" />
        <polyline points="26,36 32,26 38,36" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  learn_user_fact: {
    label: 'Learning',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="32" cy="22" r="10" />
        <path d="M26 32c-6 2-10 8-10 14h32c0-6-4-12-10-14" />
        <circle cx="32" cy="22" r="4" opacity="0.4" />
      </svg>
    ),
  },
  wait_seconds: {
    label: 'Waiting',
    svg: (
      <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M22 10h20v8l-6 10 6 10v16H22V38l6-10-6-10V10z" />
        <line x1="22" y1="10" x2="42" y2="10" strokeWidth="2" />
        <line x1="22" y1="54" x2="42" y2="54" strokeWidth="2" />
      </svg>
    ),
  },
};

// Default hologram for unknown tools
const DEFAULT_HOLO = {
  label: 'Processing',
  svg: (
    <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="32" cy="32" r="18" />
      <path d="M32 20v12l8 6" strokeLinecap="round" />
      <circle cx="32" cy="32" r="4" opacity="0.3" />
    </svg>
  ),
};

/* ── Panel positions for 1–5 simultaneous tasks ───────────── */
const SLOT_POSITIONS = [
  { top: '15%', right: '4%' },
  { top: '15%', left: '4%' },
  { top: '38%', right: '5%' },
  { top: '38%', left: '5%' },
  { top: '60%', right: '4%' },
];

/* ── Single holographic panel ─────────────────────────────── */
function HoloTask({ tool, input, result, slot, delay }) {
  const holo = TOOL_HOLOGRAMS[tool] || DEFAULT_HOLO;
  const isDone = result != null;
  const fromRight = slot % 2 === 0;

  // Build a short context label from input
  let context = '';
  if (input) {
    if (typeof input === 'string') context = input.slice(0, 40);
    else if (input.query) context = input.query.slice(0, 40);
    else if (input.location) context = input.location.slice(0, 40);
    else if (input.command) context = input.command.slice(0, 40);
    else if (input.url) context = input.url.slice(0, 40);
    else if (input.app_name) context = input.app_name;
    else if (input.path) context = input.path.split('/').pop()?.slice(0, 30) || '';
    else if (input.text) context = input.text.slice(0, 40);
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: fromRight ? 80 : -80, scale: 0.7 }}
      animate={{
        opacity: isDone ? [0.7, 0.3] : 1,
        x: 0,
        scale: 1,
      }}
      exit={{ opacity: 0, x: fromRight ? 60 : -60, scale: 0.8 }}
      transition={{
        type: 'spring', stiffness: 120, damping: 18,
        delay: delay * 0.1,
      }}
      style={{
        position: 'absolute',
        ...SLOT_POSITIONS[slot] || SLOT_POSITIONS[0],
        width: 150,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        pointerEvents: 'none',
      }}
    >
      {/* Holographic icon container */}
      <motion.div
        animate={{
          y: [0, -6, 0],
          rotateY: [0, 3, 0, -3, 0],
        }}
        transition={{
          y: { duration: 4 + delay * 0.5, repeat: Infinity, ease: 'easeInOut' },
          rotateY: { duration: 6, repeat: Infinity, ease: 'easeInOut' },
        }}
        style={{
          width: 110,
          height: 110,
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {/* Outer glow ring */}
        <div style={{
          position: 'absolute', inset: 0,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(0,180,255,0.08) 0%, rgba(0,180,255,0.02) 50%, transparent 70%)',
          border: '1px solid rgba(0,180,255,0.12)',
        }} />

        {/* Rotating ring */}
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 12, repeat: Infinity, ease: 'linear' }}
          style={{
            position: 'absolute', inset: -4,
            borderRadius: '50%',
            border: '1px solid transparent',
            borderTopColor: 'rgba(0,180,255,0.20)',
            borderRightColor: 'rgba(0,180,255,0.06)',
          }}
        />

        {/* SVG icon */}
        <div style={{
          width: 56,
          height: 56,
          color: isDone ? 'rgba(0,230,118,0.6)' : 'rgba(0,180,255,0.7)',
          filter: `drop-shadow(0 0 8px ${isDone ? 'rgba(0,230,118,0.3)' : 'rgba(0,180,255,0.4)'})`,
          transition: 'color 0.5s, filter 0.5s',
        }}>
          {holo.svg}
        </div>

        {/* Scan line */}
        <motion.div
          animate={{ top: ['10%', '90%', '10%'] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: 'linear' }}
          style={{
            position: 'absolute', left: '15%', right: '15%',
            height: 1,
            background: 'linear-gradient(90deg, transparent, rgba(0,180,255,0.15), transparent)',
          }}
        />

        {/* Corner brackets */}
        <div style={{ position: 'absolute', top: 6, left: 6, width: 10, height: 10, borderTop: '1px solid rgba(0,180,255,0.25)', borderLeft: '1px solid rgba(0,180,255,0.25)' }} />
        <div style={{ position: 'absolute', top: 6, right: 6, width: 10, height: 10, borderTop: '1px solid rgba(0,180,255,0.25)', borderRight: '1px solid rgba(0,180,255,0.25)' }} />
        <div style={{ position: 'absolute', bottom: 6, left: 6, width: 10, height: 10, borderBottom: '1px solid rgba(0,180,255,0.25)', borderLeft: '1px solid rgba(0,180,255,0.25)' }} />
        <div style={{ position: 'absolute', bottom: 6, right: 6, width: 10, height: 10, borderBottom: '1px solid rgba(0,180,255,0.25)', borderRight: '1px solid rgba(0,180,255,0.25)' }} />
      </motion.div>

      {/* Label */}
      <div style={{
        marginTop: 8,
        fontFamily: 'monospace',
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: 1.5,
        textTransform: 'uppercase',
        color: isDone ? 'rgba(0,230,118,0.6)' : 'rgba(0,180,255,0.7)',
        textAlign: 'center',
        textShadow: `0 0 10px ${isDone ? 'rgba(0,230,118,0.3)' : 'rgba(0,180,255,0.3)'}`,
        transition: 'color 0.5s',
      }}>
        {holo.label}
      </div>

      {/* Context text */}
      {context && (
        <div style={{
          marginTop: 3,
          fontFamily: 'monospace',
          fontSize: 9,
          color: 'rgba(0,180,255,0.35)',
          textAlign: 'center',
          maxWidth: 140,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {context}
        </div>
      )}

      {/* Status indicator */}
      <div style={{
        marginTop: 6,
        width: isDone ? 50 : 30,
        height: 2,
        borderRadius: 1,
        background: isDone
          ? 'linear-gradient(90deg, rgba(0,230,118,0.5), rgba(0,230,118,0.1))'
          : 'linear-gradient(90deg, rgba(0,180,255,0.4), rgba(0,180,255,0.1))',
        transition: 'width 0.5s, background 0.5s',
      }} />

      {/* Active working indicator (pulsing dots) */}
      {!isDone && (
        <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
          {[0, 1, 2].map(i => (
            <motion.div
              key={i}
              animate={{ opacity: [0.2, 0.8, 0.2] }}
              transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
              style={{
                width: 3, height: 3, borderRadius: '50%',
                background: 'rgba(0,180,255,0.6)',
              }}
            />
          ))}
        </div>
      )}
    </motion.div>
  );
}

/* ── Main display — manages visible holograms ─────────────── */
export default function HoloTaskDisplay({ toolCalls = [], state }) {
  const [visibleTasks, setVisibleTasks] = useState([]);
  const dismissTimers = useRef({});

  // Merge incoming tool calls into visible tasks (never remove unfinished ones)
  useEffect(() => {
    setVisibleTasks(prev => {
      const byKey = new Map(prev.map(t => [t.key, t]));

      // Add / update from latest toolCalls
      toolCalls.forEach((tc, i) => {
        const key = `${tc.tool}-${tc.ts || i}`;
        const existing = byKey.get(key);
        if (existing) {
          // Update result if it arrived
          byKey.set(key, { ...existing, ...tc, key, slot: i });
        } else {
          byKey.set(key, { ...tc, key, slot: i });
        }
      });

      // Keep all tasks that are NOT yet finished (result === null/undefined)
      // Also keep recently-finished ones (dismiss timer handles removal)
      return Array.from(byKey.values()).slice(-5);
    });
  }, [toolCalls]);

  // Only dismiss completed tasks 5s after the whole turn ends (state → idle/speaking)
  const prevState = useRef(state);
  useEffect(() => {
    const wasWorking = ['thinking', 'responding'].includes(prevState.current);
    const nowDone = ['idle', 'speaking', 'listening'].includes(state);
    prevState.current = state;

    if (wasWorking && nowDone) {
      // Turn ended — start fade-out timers for any completed tasks
      const timer = setTimeout(() => {
        setVisibleTasks(prev => prev.filter(t => t.result == null));
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [state]);

  // Also show a hologram while thinking (before tool calls arrive)
  const showThinking = state === 'thinking' && visibleTasks.length === 0;

  return (
    <div style={{
      position: 'absolute',
      inset: 0,
      pointerEvents: 'none',
      zIndex: 2,
      overflow: 'hidden',
    }}>
      <AnimatePresence mode="popLayout">
        {showThinking && (
          <HoloTask
            key="thinking-holo"
            tool="__thinking__"
            input={null}
            result={null}
            slot={0}
            delay={0}
          />
        )}
        {visibleTasks.map((task, i) => (
          <HoloTask
            key={task.key}
            tool={task.tool}
            input={task.input}
            result={task.result}
            slot={i}
            delay={i}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
