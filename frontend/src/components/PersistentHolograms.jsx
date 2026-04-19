import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * PersistentHolograms — Renders notes, reminders, and recent tasks
 * as interactive 3D holograms orbiting the center.
 */

// Helper to determine if a note is related to Google Keep
const isKeepNote = (text) => text.toLowerCase().includes('keep') || text.toLowerCase().includes('google keep');

function HologramCard({ data, onDismiss, onClick }) {
  const type = data.type; // 'reminder', 'note', 'task'
  const isKeep = type === 'note' && isKeepNote(data.title || data.text);

  let icon = '📝';
  let color = '100, 150, 255';
  
  if (type === 'reminder') { icon = '⏰'; color = '255, 180, 50'; }
  if (type === 'task') { icon = '⚙️'; color = '150, 255, 150'; }
  if (isKeep) { icon = '📒'; color = '255, 200, 0'; }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0 }}
      animate={{ 
        opacity: [0.6, 0.8, 0.6], 
        y: [data.y, data.y - 15, data.y], // Bobbing up and down around target y
        x: data.x,
        scale: 1,
        rotateY: [0, 5, 0, -5, 0],
      }}
      exit={{ opacity: 0, scale: 0.5, filter: 'blur(10px)' }}
      transition={{
        opacity: { duration: 4 + Math.random(), repeat: Infinity, ease: 'easeInOut' },
        rotateY: { duration: 6 + Math.random() * 2, repeat: Infinity, ease: 'easeInOut' },
        y: { duration: 3 + Math.random() * 2, repeat: Infinity, ease: 'easeInOut' },
        x: { type: 'spring', stiffness: 50, damping: 20 },
        scale: { type: 'spring', stiffness: 50, damping: 20 },
      }}
      style={{
        position: 'absolute',
        width: 140,
        height: 100,
        background: `rgba(${color}, 0.05)`,
        border: `1px solid rgba(${color}, 0.2)`,
        borderRadius: 8,
        backdropFilter: 'blur(6px)',
        cursor: 'pointer',
        pointerEvents: 'auto',
        display: 'flex',
        flexDirection: 'column',
        padding: '10px',
        boxShadow: `0 0 15px rgba(${color}, 0.1)`,
      }}
      onClick={() => onClick(data)}
      whileHover={{ scale: 1.1, zIndex: 10, background: `rgba(${color}, 0.1)` }}
    >
      {/* Close button */}
      <div 
        onClick={(e) => { e.stopPropagation(); onDismiss(data.id); }}
        style={{
          position: 'absolute', top: 4, right: 6,
          color: `rgba(${color}, 0.8)`, fontSize: 12,
          cursor: 'pointer', fontFamily: 'monospace'
        }}
      >
        ✕
      </div>
      
      <div style={{ fontSize: 18, marginBottom: 4 }}>{icon}</div>
      <div style={{
        fontFamily: 'monospace', fontSize: 10, fontWeight: 600,
        color: `rgba(${color}, 0.9)`, marginBottom: 4,
        textTransform: 'uppercase'
      }}>
        {type}
      </div>
      <div style={{
        fontFamily: 'sans-serif', fontSize: 11, color: `rgba(255,255,255,0.7)`,
        overflow: 'hidden', textOverflow: 'ellipsis',
        display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical'
      }}>
        {data.title || data.text}
      </div>
    </motion.div>
  );
}

function DetailModal({ data, onClose }) {
  if (!data) return null;
  const isKeep = data.type === 'note' && isKeepNote(data.title || data.text);

  const handleAction = () => {
    if (isKeep) {
      window.open('https://keep.google.com', '_blank');
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 100, pointerEvents: 'auto'
    }} onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.8, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 20 }}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 400,
          background: 'rgba(20, 30, 45, 0.85)',
          border: '1px solid rgba(0, 180, 255, 0.3)',
          borderRadius: 16,
          padding: 24,
          color: 'white',
          boxShadow: '0 0 40px rgba(0,180,255,0.1)',
          display: 'flex', flexDirection: 'column'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontFamily: 'monospace', color: '#00b4ff' }}>
            {data.type.toUpperCase()} DETAILS
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: 20 }}>✕</button>
        </div>

        <div style={{ fontSize: 15, lineHeight: 1.5, color: '#ccc', marginBottom: 24, whiteSpace: 'pre-wrap' }}>
          {data.text || data.title}
        </div>

        {data.type === 'reminder' && (
          <div style={{ fontSize: 12, color: '#888', marginBottom: 16, fontFamily: 'monospace' }}>
            Fires at: {new Date(data.fire_at).toLocaleTimeString()}
          </div>
        )}

        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          {isKeep && (
            <button 
              onClick={handleAction}
              style={{
                padding: '8px 16px', background: 'rgba(255, 200, 0, 0.1)',
                border: '1px solid rgba(255, 200, 0, 0.4)', borderRadius: 6,
                color: '#ffc800', cursor: 'pointer', fontFamily: 'monospace'
              }}
            >
              OPEN GOOGLE KEEP
            </button>
          )}
          <button 
            onClick={onClose}
            style={{
              padding: '8px 16px', background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: 6,
              color: '#fff', cursor: 'pointer', fontFamily: 'monospace'
            }}
          >
            CLOSE
          </button>
        </div>
      </motion.div>
    </div>
  );
}

export default function PersistentHolograms({ toolCalls = [] }) {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [dismissedIds, setDismissedIds] = useState(new Set());
  const positionsRef = useRef({}); // Store fixed random positions per id

  // Helper to get or generate fixed position
  const getFixedPosition = (id) => {
    if (!positionsRef.current[id]) {
      // Pick a random angle
      const angle = Math.random() * Math.PI * 2;
      // Distance from center: 300 to 550
      const radius = 300 + Math.random() * 250;
      
      const x = Math.cos(angle) * radius - 70; // offset by half width
      const y = Math.sin(angle) * radius * 0.6 - 50; // offset by half height
      
      positionsRef.current[id] = { x, y };
    }
    return positionsRef.current[id];
  };

  // Fetch data
  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch('http://localhost:8000/context_data');
        if (!res.ok) return;
        const data = await res.json();
        
        const newItems = [];
        
        // Reminders
        (data.reminders || []).forEach((r, i) => {
          const id = `rem-${i}-${r.fire_at}`;
          if (!dismissedIds.has(id)) {
            const pos = getFixedPosition(id);
            newItems.push({
              id,
              type: 'reminder',
              title: r.message,
              text: r.message,
              fire_at: r.fire_at,
              x: pos.x,
              y: pos.y
            });
          }
        });

        // Notes (Facts)
        (data.notes || []).forEach((n, i) => {
          const id = `not-${i}-${n.learned_at}`;
          if (!dismissedIds.has(id)) {
            const pos = getFixedPosition(id);
            newItems.push({
              id,
              type: 'note',
              title: n.fact,
              text: n.fact,
              learned_at: n.learned_at,
              x: pos.x,
              y: pos.y
            });
          }
        });

        // Previous tasks
        const recentTasks = toolCalls.filter(tc => tc.result).slice(-3);
        recentTasks.forEach((tc) => {
          const id = `tsk-${tc.ts || tc.tool}`;
          if (!dismissedIds.has(id)) {
            const pos = getFixedPosition(id);
            newItems.push({
              id,
              type: 'task',
              title: tc.tool,
              text: `Result: ${tc.result}`,
              x: pos.x,
              y: pos.y
            });
          }
        });

        setItems(newItems);
      } catch (e) {
        console.error('Failed to fetch context data', e);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, [toolCalls, dismissedIds]);

  const handleDismiss = (id) => {
    setDismissedIds(prev => new Set(prev).add(id));
    if (selected && selected.id === id) setSelected(null);
  };

  return (
    <>
      <div style={{
        position: 'absolute',
        top: '50%', left: '50%',
        width: 0, height: 0,
        zIndex: 4,
      }}>
        <AnimatePresence>
          {items.map((item) => (
            <HologramCard
              key={item.id}
              data={item}
              onDismiss={handleDismiss}
              onClick={setSelected}
            />
          ))}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {selected && <DetailModal data={selected} onClose={() => setSelected(null)} />}
      </AnimatePresence>
    </>
  );
}
