import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * ContextPanel — collapsible side panel showing last tool results.
 * Shows screenshots, calendar data, terminal output, etc.
 */

const styles = {
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: 340,
    height: '100%',
    background: 'rgba(8,10,18,0.95)',
    borderRight: '1px solid rgba(255,255,255,0.06)',
    backdropFilter: 'blur(20px)',
    zIndex: 5,
    overflowY: 'auto',
    padding: '60px 16px 16px',
  },
  title: {
    fontFamily: 'monospace',
    fontSize: 10,
    letterSpacing: 2,
    textTransform: 'uppercase',
    color: '#556677',
    marginBottom: 16,
  },
  card: {
    background: 'rgba(255,255,255,0.02)',
    border: '1px solid rgba(255,255,255,0.06)',
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
  },
  toolName: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#0af',
    marginBottom: 6,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  input: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#667788',
    marginBottom: 6,
    wordBreak: 'break-all',
  },
  result: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#99aabb',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    maxHeight: 200,
    overflowY: 'auto',
    lineHeight: 1.5,
  },
  emptyState: {
    fontFamily: 'monospace',
    fontSize: 12,
    color: '#334455',
    textAlign: 'center',
    marginTop: 60,
  },
  spinner: {
    display: 'inline-block',
    width: 8,
    height: 8,
    borderRadius: '50%',
    border: '1.5px solid transparent',
    borderTopColor: '#0af',
  },
};

const TOOL_ICONS = {
  take_screenshot: '📸',
  get_calendar_events: '📅',
  get_emails: '📧',
  read_file: '📄',
  list_directory: '📁',
  run_terminal_command: '💻',
  open_browser: '🌐',
  browser_search: '🔍',
  browser_agent: '🤖',
  create_note: '📝',
};

export default function ContextPanel({ open, toolCalls = [] }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ x: -340, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: -340, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 250 }}
          style={styles.overlay}
        >
          <div style={styles.title}>History</div>

          {toolCalls.length === 0 ? (
            <div style={styles.emptyState}>
              No activity yet.<br />
              Ask JARVIS something that needs<br />
              screen, files, or search access.
            </div>
          ) : (
            [...toolCalls].reverse().map((call, i) => (
              <motion.div
                key={`${call.tool}-${call.ts}-${i}`}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                style={styles.card}
              >
                <div style={styles.toolName}>
                  <span>{TOOL_ICONS[call.tool] || '🔧'}</span>
                  <span>{call.tool}</span>
                  {!call.result && (
                    <motion.span
                      style={styles.spinner}
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    />
                  )}
                </div>

                {call.input && Object.keys(call.input).length > 0 && (
                  <div style={styles.input}>
                    {Object.entries(call.input).map(([k, v]) => (
                      <div key={k}>{k}: {typeof v === 'string' ? v : JSON.stringify(v)}</div>
                    ))}
                  </div>
                )}

                {call.tool === 'browser_agent' && call.browserStep && !call.result && (
                  <div style={{ ...styles.input, borderLeft: '2px solid #00d4ff', marginTop: 6 }}>
                    <div style={{ color: '#00d4ff', fontSize: 11, fontWeight: 600 }}>
                      🌐 {call.browserSummary || `Step ${call.browserStep}`}
                    </div>
                    {call.browserUrl && (
                      <div style={{ fontSize: 10, opacity: 0.6, marginTop: 2, wordBreak: 'break-all' }}>
                        {call.browserUrl}
                      </div>
                    )}
                  </div>
                )}

                {call.result && (
                  <div style={styles.result}>
                    {call.result}
                  </div>
                )}
              </motion.div>
            ))
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
