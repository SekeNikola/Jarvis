import React, { useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * Transcript — shows the live voice transcript and Claude's response.
 * Scrolling, monospaced, HUD-style.
 */

const styles = {
  container: {
    width: '90%',
    maxWidth: 650,
    maxHeight: 200,
    marginTop: 24,
    overflow: 'hidden',
    position: 'relative',
  },
  userLine: {
    fontFamily: '"SF Mono", "Fira Code", "Cascadia Code", monospace',
    fontSize: 14,
    lineHeight: 1.7,
    color: '#8899aa',
    padding: '6px 0',
    userSelect: 'text',
    cursor: 'text',
  },
  responseLine: {
    fontFamily: '"SF Mono", "Fira Code", "Cascadia Code", monospace',
    fontSize: 14,
    lineHeight: 1.7,
    color: '#d0dce8',
    padding: '6px 0',
    userSelect: 'text',
    cursor: 'text',
  },
  label: {
    fontFamily: 'monospace',
    fontSize: 10,
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    marginBottom: 4,
    opacity: 0.4,
  },
  // Fade gradient at top
  fadeTop: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: 30,
    background: 'linear-gradient(to bottom, #0a0a0f, transparent)',
    pointerEvents: 'none',
    zIndex: 2,
  },
};

export default function Transcript({ state, transcript, response }) {
  const scrollRef = useRef(null);

  // Auto-scroll as content streams in
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript, response]);

  const showTranscript = transcript && transcript.trim();
  const showResponse = response && response.trim();

  if (!showTranscript && !showResponse) return null;

  return (
    <div style={styles.container}>
      <div style={styles.fadeTop} />
      <div
        ref={scrollRef}
        style={{
          maxHeight: 200,
          overflowY: 'auto',
          paddingTop: 30,
          scrollBehavior: 'smooth',
          // Hide scrollbar
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
        }}
      >
        {/* User transcript */}
        <AnimatePresence>
          {showTranscript && (
            <motion.div
              key="transcript"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              <div style={{ ...styles.label, color: '#0af' }}>YOU</div>
              <div style={styles.userLine}>{transcript}</div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Claude response */}
        <AnimatePresence>
          {showResponse && (
            <motion.div
              key="response"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              style={{ marginTop: 12 }}
            >
              <div style={{ ...styles.label, color: '#a070ff' }}>JARVIS</div>
              <div style={styles.responseLine}>
                {response}
                {/* Blinking cursor while responding */}
                {(state === 'responding' || state === 'thinking') && (
                  <motion.span
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.8, repeat: Infinity }}
                    style={{ color: '#a070ff' }}
                  >
                    ▌
                  </motion.span>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
