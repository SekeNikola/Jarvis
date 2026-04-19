import React, { useRef, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * HolographicSpace — 3D background inspired by Tony Stark's lab.
 *
 * Renders floating holographic panels in a CSS 3D perspective space.
 * Each panel represents an active JARVIS subsystem or recent tool activity.
 * Panels slowly rotate and drift, with a grid floor and particle dust.
 */

// Holographic grid floor drawn on canvas
function GridFloor() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width = window.innerWidth;
    const h = canvas.height = window.innerHeight;

    let t = 0;
    const draw = () => {
      ctx.clearRect(0, 0, w, h);

      // Perspective grid
      const horizon = h * 0.55;
      const vanishX = w / 2;

      // Horizontal lines (receding into distance)
      for (let i = 0; i < 20; i++) {
        const progress = i / 20;
        const y = horizon + (h - horizon) * Math.pow(progress, 1.5);
        const alpha = 0.03 + progress * 0.04;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.strokeStyle = `rgba(0, 150, 255, ${alpha})`;
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }

      // Vertical lines (converging to vanishing point)
      for (let i = -15; i <= 15; i++) {
        const spread = i * 80;
        const alpha = 0.02 + Math.abs(i) * 0.002;
        ctx.beginPath();
        ctx.moveTo(vanishX + spread * 3, h);
        ctx.lineTo(vanishX + spread * 0.1, horizon);
        ctx.strokeStyle = `rgba(0, 150, 255, ${alpha})`;
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }

      // Floating dust particles
      for (let i = 0; i < 40; i++) {
        const seed = i * 137.508;
        const x = (Math.sin(seed + t * 0.0003 * (i % 5 + 1)) * 0.5 + 0.5) * w;
        const y = (Math.cos(seed * 0.7 + t * 0.0002 * (i % 3 + 1)) * 0.5 + 0.5) * h;
        const size = 0.5 + Math.sin(seed) * 0.5;
        const alpha = 0.1 + Math.sin(t * 0.002 + i) * 0.05;

        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(0, 180, 255, ${alpha})`;
        ctx.fill();
      }

      t++;
      requestAnimationFrame(draw);
    };

    const raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute', top: 0, left: 0,
        width: '100%', height: '100%',
        pointerEvents: 'none', opacity: 0.6,
      }}
    />
  );
}


// Floating holographic panel
function HoloPanel({ label, icon, status, style, delay = 0 }) {
  const isActive = status === 'ok';
  const color = isActive ? '0, 180, 255' : '100, 120, 140';

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{
        opacity: [0.3, 0.5, 0.3],
        scale: 1,
        y: [0, -6, 0],
      }}
      transition={{
        opacity: { duration: 4, repeat: Infinity, delay },
        scale: { duration: 0.8, delay: delay * 0.3 },
        y: { duration: 5 + delay, repeat: Infinity, ease: 'easeInOut' },
      }}
      style={{
        position: 'absolute',
        ...style,
        width: 120,
        padding: '12px 14px',
        background: `rgba(${color}, 0.04)`,
        border: `1px solid rgba(${color}, 0.12)`,
        borderRadius: 8,
        backdropFilter: 'blur(4px)',
        pointerEvents: 'none',
        transformStyle: 'preserve-3d',
      }}
    >
      <div style={{
        fontFamily: 'monospace', fontSize: 16, marginBottom: 4,
        color: `rgba(${color}, 0.8)`,
      }}>
        {icon}
      </div>
      <div style={{
        fontFamily: 'monospace', fontSize: 9, fontWeight: 500,
        letterSpacing: 1, textTransform: 'uppercase',
        color: `rgba(${color}, 0.6)`,
      }}>
        {label}
      </div>
      {/* Status line */}
      <div style={{
        marginTop: 6, height: 2, borderRadius: 1,
        background: isActive
          ? `linear-gradient(90deg, rgba(0,230,118,0.4), rgba(0,230,118,0.1))`
          : `linear-gradient(90deg, rgba(100,120,140,0.2), transparent)`,
        width: isActive ? '80%' : '40%',
        transition: 'width 0.5s, background 0.5s',
      }} />
      {/* Scan line effect */}
      <motion.div
        animate={{ top: ['0%', '100%', '0%'] }}
        transition={{ duration: 3 + delay, repeat: Infinity, ease: 'linear' }}
        style={{
          position: 'absolute', left: 0, right: 0, height: 1,
          background: `linear-gradient(90deg, transparent, rgba(${color}, 0.1), transparent)`,
          pointerEvents: 'none',
        }}
      />
    </motion.div>
  );
}


// Tool activity card that fades in/out
function ToolActivity({ tool, isActive }) {
  return (
    <AnimatePresence>
      {isActive && (
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 0.5 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.5 }}
          style={{
            padding: '6px 12px', borderRadius: 6, marginBottom: 4,
            background: 'rgba(160, 112, 255, 0.06)',
            border: '1px solid rgba(160, 112, 255, 0.1)',
            fontFamily: 'monospace', fontSize: 9, color: 'rgba(160, 112, 255, 0.5)',
            letterSpacing: 0.5,
          }}
        >
          ▸ {tool}
        </motion.div>
      )}
    </AnimatePresence>
  );
}


// Panel layout positions (spread around the orb center)
const PANEL_POSITIONS = [
  { top: '8%',  left: '3%',  icon: '🧠', label: 'Gemini',  key: 'gemini' },
  { top: '22%', left: '6%',  icon: '🔊', label: 'TTS',     key: 'tts' },
  { top: '8%',  right: '3%', icon: '🎤', label: 'Whisper',  key: 'whisper' },
  { top: '22%', right: '6%', icon: '👁', label: 'Vision',   key: 'screen_vision' },
  { bottom: '22%', left: '4%',  icon: '📁', label: 'Files', key: 'filesystem' },
  { bottom: '8%',  left: '3%',  icon: '💻', label: 'Terminal', key: 'terminal' },
  { bottom: '22%', right: '4%', icon: '🌐', label: 'Browser', key: 'browser' },
];


export default function HolographicSpace({ integrations = {}, toolCalls = [], state }) {
  // Get recent active tools (last 3)
  const recentTools = toolCalls.slice(-3).map(tc => tc.tool);

  return (
    <div style={{
      position: 'absolute', inset: 0,
      perspective: '1200px',
      perspectiveOrigin: '50% 45%',
      pointerEvents: 'none',
      zIndex: 0,
      overflow: 'hidden',
    }}>
      {/* Grid floor */}
      <GridFloor />

      {/* Ambient horizontal scan line */}
      <motion.div
        animate={{ top: ['-2%', '102%'] }}
        transition={{ duration: 8, repeat: Infinity, ease: 'linear' }}
        style={{
          position: 'absolute', left: 0, right: 0, height: 1,
          background: 'linear-gradient(90deg, transparent, rgba(0,150,255,0.06), transparent)',
          pointerEvents: 'none',
        }}
      />

      {/* Corner decorations — HUD brackets */}
      <div style={{ position: 'absolute', top: 50, left: 20, width: 30, height: 30, borderTop: '1px solid rgba(0,150,255,0.08)', borderLeft: '1px solid rgba(0,150,255,0.08)' }} />
      <div style={{ position: 'absolute', top: 50, right: 20, width: 30, height: 30, borderTop: '1px solid rgba(0,150,255,0.08)', borderRight: '1px solid rgba(0,150,255,0.08)' }} />
      <div style={{ position: 'absolute', bottom: 70, left: 20, width: 30, height: 30, borderBottom: '1px solid rgba(0,150,255,0.08)', borderLeft: '1px solid rgba(0,150,255,0.08)' }} />
      <div style={{ position: 'absolute', bottom: 70, right: 20, width: 30, height: 30, borderBottom: '1px solid rgba(0,150,255,0.08)', borderRight: '1px solid rgba(0,150,255,0.08)' }} />
    </div>
  );
}
