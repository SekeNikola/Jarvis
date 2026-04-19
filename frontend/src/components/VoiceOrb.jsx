import React, { useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * ParticleOrb — particles.js-style connected-dot network in a circle.
 *
 * 2D particles drift freely inside a circular boundary.
 * All nearby pairs are connected with fading lines.
 * The boundary radius, speed, and colours react to JARVIS state.
 * Sits behind transcript text (z-index 0, absolutely positioned).
 */

const STATE_CONFIG = {
  idle:         { hue: 200, sat: 60, light: 55, boundaryR: 280, speed: 0.35, lineDist: 110, lineAlpha: 0.18, dotAlpha: 0.55, pulseAmp: 0.02, label: 'Ready' },
  listening:    { hue: 190, sat: 90, light: 70, boundaryR: 340, speed: 1.2,  lineDist: 130, lineAlpha: 0.35, dotAlpha: 0.75, pulseAmp: 0.12, label: 'Listening…' },
  transcribing: { hue: 190, sat: 80, light: 60, boundaryR: 310, speed: 0.8,  lineDist: 120, lineAlpha: 0.25, dotAlpha: 0.65, pulseAmp: 0.08, label: 'Transcribing…' },
  thinking:     { hue: 35,  sat: 85, light: 60, boundaryR: 300, speed: 1.6,  lineDist: 115, lineAlpha: 0.28, dotAlpha: 0.65, pulseAmp: 0.04, label: 'Thinking…' },
  responding:   { hue: 270, sat: 70, light: 65, boundaryR: 320, speed: 0.7,  lineDist: 125, lineAlpha: 0.25, dotAlpha: 0.65, pulseAmp: 0.08, label: '' },
  speaking:     { hue: 160, sat: 80, light: 60, boundaryR: 360, speed: 0.6,  lineDist: 140, lineAlpha: 0.40, dotAlpha: 0.80, pulseAmp: 0.18, label: 'Speaking…' },
};

const PARTICLE_COUNT = 120;
const CANVAS_SIZE = 800;
const CENTER = CANVAS_SIZE / 2;

/** Spawn particles uniformly inside a circle */
function createParticles(count) {
  const particles = [];
  for (let i = 0; i < count; i++) {
    // Random position inside unit circle (uniform)
    const angle = Math.random() * Math.PI * 2;
    const r = Math.sqrt(Math.random()); // sqrt for uniform area distribution
    const speed = 0.3 + Math.random() * 0.7;
    const dir = Math.random() * Math.PI * 2;
    particles.push({
      // Normalised position (−1…1), will be scaled by boundaryR
      nx: r * Math.cos(angle),
      ny: r * Math.sin(angle),
      // Velocity (pixels/frame at base speed 1)
      vx: Math.cos(dir) * speed,
      vy: Math.sin(dir) * speed,
      size: 1.5 + Math.random() * 2.5,
      brightness: 0.4 + Math.random() * 0.6,
    });
  }
  return particles;
}

export default function VoiceOrb({ state = 'idle', onClick, audioLevel = 0 }) {
  const canvasRef = useRef(null);
  const particlesRef = useRef(createParticles(PARTICLE_COUNT));
  const animRef = useRef(null);
  const targetRef = useRef(STATE_CONFIG.idle);
  const curRef = useRef({ ...STATE_CONFIG.idle });
  const timeRef = useRef(0);

  useEffect(() => {
    targetRef.current = STATE_CONFIG[state] || STATE_CONFIG.idle;
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = CANVAS_SIZE * dpr;
    canvas.height = CANVAS_SIZE * dpr;
    ctx.scale(dpr, dpr);

    const particles = particlesRef.current;

    const animate = () => {
      timeRef.current += 0.016;
      const t = timeRef.current;

      // ── Smooth lerp toward target ──
      const tgt = targetRef.current;
      const c = curRef.current;
      const L = 0.035;
      for (const k of ['hue','sat','light','boundaryR','speed','lineDist','lineAlpha','dotAlpha','pulseAmp']) {
        c[k] += (tgt[k] - c[k]) * L;
      }

      const pulse = 1 + Math.sin(t * 2.5) * c.pulseAmp;
      const bR = c.boundaryR * pulse; // current circular boundary radius

      ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

      // ── Subtle background glow ──
      const glow = ctx.createRadialGradient(CENTER, CENTER, 0, CENTER, CENTER, bR * 1.1);
      glow.addColorStop(0, `hsla(${c.hue}, ${c.sat}%, ${c.light}%, 0.06)`);
      glow.addColorStop(0.7, `hsla(${c.hue}, ${c.sat}%, ${c.light}%, 0.015)`);
      glow.addColorStop(1, 'transparent');
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

      // ── Update particle positions (2D, free movement) ──
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        // Move in pixel space
        p.nx += p.vx * c.speed * 0.003;
        p.ny += p.vy * c.speed * 0.003;

        // Bounce off circular boundary
        const dist = Math.sqrt(p.nx * p.nx + p.ny * p.ny);
        if (dist > 1) {
          // Reflect velocity off the boundary normal
          const nx = p.nx / dist;
          const ny = p.ny / dist;
          const dot = p.vx * nx + p.vy * ny;
          p.vx -= 2 * dot * nx;
          p.vy -= 2 * dot * ny;
          // Push back inside
          p.nx = nx * 0.99;
          p.ny = ny * 0.99;
        }
      }

      // ── Compute screen positions ──
      const screenPos = [];
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        screenPos.push({
          x: CENTER + p.nx * bR,
          y: CENTER + p.ny * bR,
          size: p.size,
          brightness: p.brightness,
        });
      }

      // ── Draw connecting lines (all pairs, true particles.js style) ──
      const ld = c.lineDist;
      const ldSq = ld * ld;
      ctx.lineWidth = 0.8;
      for (let i = 0; i < screenPos.length; i++) {
        const a = screenPos[i];
        for (let j = i + 1; j < screenPos.length; j++) {
          const b = screenPos[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dSq = dx * dx + dy * dy;
          if (dSq < ldSq) {
            const fade = 1 - Math.sqrt(dSq) / ld;
            const alpha = fade * c.lineAlpha;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.strokeStyle = `hsla(${c.hue}, ${c.sat - 10}%, ${c.light + 20}%, ${alpha})`;
            ctx.stroke();
          }
        }
      }

      // ── Draw particles ──
      for (let i = 0; i < screenPos.length; i++) {
        const s = screenPos[i];
        const alpha = s.brightness * c.dotAlpha;

        // Dot
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${c.hue + (s.brightness - 0.5) * 20}, ${c.sat}%, ${c.light + 15}%, ${alpha})`;
        ctx.fill();

        // Soft bloom
        if (s.size > 2) {
          ctx.beginPath();
          ctx.arc(s.x, s.y, s.size * 4, 0, Math.PI * 2);
          ctx.fillStyle = `hsla(${c.hue}, ${c.sat}%, ${c.light}%, ${alpha * 0.08})`;
          ctx.fill();
        }
      }

      // ── Boundary ring (very subtle) ──
      ctx.beginPath();
      ctx.arc(CENTER, CENTER, bR, 0, Math.PI * 2);
      ctx.strokeStyle = `hsla(${c.hue}, ${c.sat}%, ${c.light}%, 0.06)`;
      ctx.lineWidth = 1;
      ctx.stroke();

      animRef.current = requestAnimationFrame(animate);
    };

    animRef.current = requestAnimationFrame(animate);
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current); };
  }, []);

  const config = STATE_CONFIG[state] || STATE_CONFIG.idle;

  return (
    <div style={{
      position: 'absolute',
      top: '50%', left: '50%',
      transform: 'translate(-50%, -50%)',
      width: CANVAS_SIZE, height: CANVAS_SIZE,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1,
      pointerEvents: 'none',
    }}>
      <canvas
        ref={canvasRef}
        style={{
          width: CANVAS_SIZE, height: CANVAS_SIZE,
          cursor: ['idle', 'listening', 'transcribing'].includes(state) ? 'pointer' : 'default',
          pointerEvents: 'auto',
        }}
        onClick={onClick}
      />

      {/* State label */}
      <AnimatePresence>
        {config.label && (
          <motion.div
            key={state}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 0.6, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            style={{
              position: 'absolute',
              bottom: 100,
              fontFamily: 'monospace',
              fontSize: 11,
              color: `hsl(${config.hue}, ${config.sat}%, ${config.light}%)`,
              letterSpacing: 2,
              textTransform: 'uppercase',
              pointerEvents: 'none',
            }}
          >
            {config.label}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Thinking spinner */}
      {state === 'thinking' && (
        <motion.div
          style={{
            position: 'absolute',
            width: 240, height: 240,
            borderRadius: '50%',
            border: '1.5px solid transparent',
            borderTopColor: `hsl(${config.hue}, ${config.sat}%, ${config.light}%)`,
            borderRightColor: `hsla(${config.hue}, ${config.sat}%, ${config.light}%, 0.3)`,
            pointerEvents: 'none',
          }}
          animate={{ rotate: 360 }}
          transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
        />
      )}
    </div>
  );
}
