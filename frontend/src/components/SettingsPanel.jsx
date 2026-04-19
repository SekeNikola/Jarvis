import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * SettingsPanel — slide-out panel with two tabs:
 *   1. Preferences  — configure default apps (notes, calendar, etc.)
 *   2. Profile       — manage email accounts, contacts, facts, work, routines
 */

const API_BASE = 'http://localhost:8000';

const CATEGORY_ICONS = {
  notes_app: '📝',
  calendar_app: '📅',
  email_app: '📧',
  browser: '🌐',
  music_app: '🎵',
  messenger_app: '💬',
  maps_app: '🗺️',
  search_engine: '🔍',
  code_editor: '💻',
  default_language: '🌍',
};

/* ── Styles ─────────────────────────────────────────── */
const s = {
  overlay: {
    position: 'absolute', top: 0, right: 0, width: 390, height: '100%',
    background: 'rgba(8,10,18,0.97)', borderLeft: '1px solid rgba(255,255,255,0.06)',
    backdropFilter: 'blur(24px)', zIndex: 20, overflowY: 'auto', padding: '24px 20px 40px',
  },
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 },
  title: { fontFamily: 'monospace', fontSize: 14, fontWeight: 600, letterSpacing: 1.5, textTransform: 'uppercase', color: '#8899aa' },
  closeBtn: { background: 'none', border: 'none', color: '#667', cursor: 'pointer', fontSize: 18, padding: '4px 8px', borderRadius: 6 },
  tabs: { display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid rgba(255,255,255,0.06)' },
  tab: (active) => ({
    fontFamily: 'monospace', fontSize: 12, fontWeight: 500, padding: '8px 16px',
    background: 'none', border: 'none', cursor: 'pointer',
    color: active ? '#0af' : '#556677', borderBottom: active ? '2px solid #0af' : '2px solid transparent',
    transition: 'color 0.2s, border-color 0.2s',
  }),
  subtitle: { fontFamily: 'monospace', fontSize: 11, color: '#445566', marginBottom: 20, lineHeight: 1.5 },
  group: { marginBottom: 16 },
  label: { fontFamily: 'monospace', fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 },
  desc: { fontFamily: 'monospace', fontSize: 10, color: '#445566', marginBottom: 8 },
  select: {
    width: '100%', padding: '10px 14px', background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, color: '#c8d0d8',
    fontSize: 13, fontFamily: 'monospace', outline: 'none', cursor: 'pointer',
    WebkitAppearance: 'none', appearance: 'none',
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%23667788' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E")`,
    backgroundRepeat: 'no-repeat', backgroundPosition: 'right 12px center', backgroundSize: '12px', paddingRight: 36,
  },
  input: {
    width: '100%', padding: '8px 12px', background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, color: '#c8d0d8',
    fontSize: 12, fontFamily: 'monospace', outline: 'none', boxSizing: 'border-box',
  },
  inputSmall: {
    flex: 1, padding: '7px 10px', background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, color: '#c8d0d8',
    fontSize: 11, fontFamily: 'monospace', outline: 'none', minWidth: 0,
  },
  btn: {
    padding: '6px 14px', background: 'rgba(0,170,255,0.12)', border: '1px solid rgba(0,170,255,0.25)',
    borderRadius: 6, color: '#0af', fontSize: 11, fontFamily: 'monospace', cursor: 'pointer',
    transition: 'background 0.2s',
  },
  btnDanger: {
    padding: '4px 8px', background: 'rgba(255,60,60,0.08)', border: '1px solid rgba(255,60,60,0.2)',
    borderRadius: 5, color: '#f66', fontSize: 10, fontFamily: 'monospace', cursor: 'pointer',
  },
  card: {
    background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
    borderRadius: 8, padding: '10px 12px', marginBottom: 8, display: 'flex',
    alignItems: 'center', justifyContent: 'space-between', gap: 10,
  },
  cardInfo: { flex: 1, minWidth: 0 },
  cardMain: { fontFamily: 'monospace', fontSize: 12, color: '#c8d0d8', wordBreak: 'break-all' },
  cardSub: { fontFamily: 'monospace', fontSize: 10, color: '#556677', marginTop: 2 },
  badge: (active) => ({
    display: 'inline-block', fontFamily: 'monospace', fontSize: 9, fontWeight: 600,
    padding: '2px 6px', borderRadius: 4, marginLeft: 6,
    background: active ? 'rgba(0,255,136,0.12)' : 'rgba(255,255,255,0.04)',
    color: active ? '#0f8' : '#556',
  }),
  savedBadge: { fontFamily: 'monospace', fontSize: 10, color: '#0f8', marginLeft: 8, transition: 'opacity 0.3s' },
  divider: { border: 'none', borderTop: '1px solid rgba(255,255,255,0.04)', margin: '20px 0' },
  sectionTitle: { fontFamily: 'monospace', fontSize: 12, fontWeight: 600, color: '#6688aa', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 },
  empty: { fontFamily: 'monospace', fontSize: 11, color: '#334455', fontStyle: 'italic', marginBottom: 12 },
  loading: { fontFamily: 'monospace', fontSize: 12, color: '#445566', textAlign: 'center', marginTop: 60 },
  error: { fontFamily: 'monospace', fontSize: 12, color: '#ff6666', textAlign: 'center', marginTop: 60 },
  row: { display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' },
  footer: { fontFamily: 'monospace', fontSize: 10, color: '#334455', textAlign: 'center', lineHeight: 1.6 },
};


/* ─────────────────────────── PREFERENCES TAB ─────────────── */
function PreferencesTab() {
  const [schema, setSchema] = useState(null);
  const [preferences, setPreferences] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [savedKey, setSavedKey] = useState(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API_BASE}/preferences/schema`).then(r => r.json()),
      fetch(`${API_BASE}/preferences`).then(r => r.json()),
    ]).then(([sr, pr]) => { setSchema(sr.schema); setPreferences(pr.preferences); setLoading(false); })
      .catch(() => { setError('Failed to load settings'); setLoading(false); });
  }, []);

  const handleChange = useCallback((key, value) => {
    setPreferences(prev => ({ ...prev, [key]: value }));
    fetch(`${API_BASE}/preferences`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preferences: { [key]: value } }),
    }).then(r => r.json()).then(res => { setPreferences(res.preferences); setSavedKey(key); setTimeout(() => setSavedKey(null), 1500); })
      .catch(err => console.error('Save error:', err));
  }, []);

  const orderedKeys = schema ? [
    'notes_app', 'calendar_app', 'email_app', 'browser', 'music_app',
    'messenger_app', 'maps_app', 'search_engine', 'code_editor', 'default_language',
  ].filter(k => k in schema) : [];

  if (loading) return <div style={s.loading}>Loading settings...</div>;
  if (error) return <div style={s.error}>⚠ {error}</div>;

  return (
    <>
      <div style={s.subtitle}>
        Configure your default apps so JARVIS knows exactly where to save notes,
        check calendar, play music, and more.
      </div>
      {orderedKeys.map(key => {
        const item = schema[key];
        const icon = CATEGORY_ICONS[key] || '⚙';
        return (
          <div key={key} style={s.group}>
            <div style={s.label}>
              <span>{icon}</span><span>{item.label}</span>
              <span style={{ ...s.savedBadge, opacity: savedKey === key ? 1 : 0 }}>✓ saved</span>
            </div>
            <div style={s.desc}>{item.description}</div>
            <select value={preferences[key] || item.default} onChange={e => handleChange(key, e.target.value)} style={s.select}>
              {item.options.map(opt => (
                <option key={opt.value} value={opt.value} style={{ background: '#0a0a0f', color: '#c8d0d8' }}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        );
      })}
    </>
  );
}


/* ─────────────────────────── PROFILE TAB ─────────────────── */
function ProfileTab() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  // Form states
  const [newEmail, setNewEmail] = useState('');
  const [newEmailLabel, setNewEmailLabel] = useState('');
  const [newContactName, setNewContactName] = useState('');
  const [newContactRelation, setNewContactRelation] = useState('');
  const [newContactPhone, setNewContactPhone] = useState('');
  const [newContactEmail, setNewContactEmail] = useState('');
  const [newFact, setNewFact] = useState('');

  const fetchProfile = useCallback(() => {
    fetch(`${API_BASE}/profile`).then(r => r.json())
      .then(res => { setProfile(res.profile); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);

  const addEmail = () => {
    if (!newEmail.trim()) return;
    fetch(`${API_BASE}/profile/email`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address: newEmail.trim(), label: newEmailLabel.trim(), default: false }),
    }).then(r => r.json()).then(res => { setProfile(res.profile); setNewEmail(''); setNewEmailLabel(''); });
  };

  const setDefaultEmail = (address) => {
    fetch(`${API_BASE}/profile/email`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, default: true }),
    }).then(r => r.json()).then(res => setProfile(res.profile));
  };

  const removeEmail = (address) => {
    const emails = (profile?.accounts?.email || []).filter(e => e.address !== address);
    fetch(`${API_BASE}/profile`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: { accounts: { ...profile.accounts, email: emails } } }),
    }).then(r => r.json()).then(res => setProfile(res.profile));
  };

  const addContact = () => {
    if (!newContactName.trim()) return;
    fetch(`${API_BASE}/profile/contact`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newContactName.trim(), relation: newContactRelation.trim(),
        phone: newContactPhone.trim(), email: newContactEmail.trim(),
      }),
    }).then(r => r.json()).then(res => {
      setProfile(res.profile);
      setNewContactName(''); setNewContactRelation(''); setNewContactPhone(''); setNewContactEmail('');
    });
  };

  const removeContact = (name) => {
    const contacts = (profile?.contacts || []).filter(c => c.name !== name);
    fetch(`${API_BASE}/profile`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: { contacts } }),
    }).then(r => r.json()).then(res => setProfile(res.profile));
  };

  const addFact = () => {
    if (!newFact.trim()) return;
    fetch(`${API_BASE}/profile/fact`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fact: newFact.trim() }),
    }).then(r => r.json()).then(res => { setProfile(res.profile); setNewFact(''); });
  };

  const removeFact = (factText) => {
    fetch(`${API_BASE}/profile/fact`, {
      method: 'DELETE', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fact: factText }),
    }).then(r => r.json()).then(res => setProfile(res.profile));
  };

  const updateWorkField = (field, value) => {
    fetch(`${API_BASE}/profile`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: { work: { ...profile.work, [field]: value } } }),
    }).then(r => r.json()).then(res => setProfile(res.profile));
  };

  const updateRoutineField = (field, value) => {
    fetch(`${API_BASE}/profile`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: { routines: { ...profile.routines, [field]: value } } }),
    }).then(r => r.json()).then(res => setProfile(res.profile));
  };

  const updateLocationField = (field, value) => {
    fetch(`${API_BASE}/profile`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: { locations: { ...profile.locations, [field]: value } } }),
    }).then(r => r.json()).then(res => setProfile(res.profile));
  };

  if (loading) return <div style={s.loading}>Loading profile...</div>;
  if (!profile) return <div style={s.error}>⚠ Failed to load profile</div>;

  const emails = profile.accounts?.email || [];
  const contacts = profile.contacts || [];
  const facts = profile.facts || [];
  const work = profile.work || {};
  const routines = profile.routines || {};
  const locations = profile.locations || {};

  return (
    <>
      <div style={s.subtitle}>
        Your personal profile — JARVIS uses this to personalize responses.
        The AI also learns facts automatically during conversations.
      </div>

      {/* ── Email Accounts ── */}
      <div style={s.sectionTitle}>📧 Email Accounts</div>
      {emails.length === 0 && <div style={s.empty}>No email accounts yet.</div>}
      {emails.map(acc => (
        <div key={acc.address} style={s.card}>
          <div style={s.cardInfo}>
            <div style={s.cardMain}>
              {acc.address}
              {acc.default && <span style={s.badge(true)}>DEFAULT</span>}
            </div>
            <div style={s.cardSub}>
              {acc.provider}{acc.label ? ` · ${acc.label}` : ''}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            {!acc.default && (
              <button style={s.btn} onClick={() => setDefaultEmail(acc.address)} title="Set as default">★</button>
            )}
            <button style={s.btnDanger} onClick={() => removeEmail(acc.address)}>✕</button>
          </div>
        </div>
      ))}
      <div style={s.row}>
        <input style={s.inputSmall} placeholder="email@example.com" value={newEmail} onChange={e => setNewEmail(e.target.value)} onKeyDown={e => e.key === 'Enter' && addEmail()} />
        <input style={{ ...s.inputSmall, maxWidth: 80 }} placeholder="label" value={newEmailLabel} onChange={e => setNewEmailLabel(e.target.value)} onKeyDown={e => e.key === 'Enter' && addEmail()} />
        <button style={s.btn} onClick={addEmail}>+</button>
      </div>

      <hr style={s.divider} />

      {/* ── Contacts ── */}
      <div style={s.sectionTitle}>👥 Contacts</div>
      {contacts.length === 0 && <div style={s.empty}>No contacts yet.</div>}
      {contacts.map(c => (
        <div key={c.name} style={s.card}>
          <div style={s.cardInfo}>
            <div style={s.cardMain}>
              {c.name}
              {c.relation && <span style={{ ...s.cardSub, marginLeft: 6, display: 'inline' }}>({c.relation})</span>}
            </div>
            <div style={s.cardSub}>
              {[c.phone, c.email, c.notes].filter(Boolean).join(' · ') || 'No details'}
            </div>
          </div>
          <button style={s.btnDanger} onClick={() => removeContact(c.name)}>✕</button>
        </div>
      ))}
      <div style={s.row}>
        <input style={s.inputSmall} placeholder="Name" value={newContactName} onChange={e => setNewContactName(e.target.value)} />
        <input style={{ ...s.inputSmall, maxWidth: 80 }} placeholder="Relation" value={newContactRelation} onChange={e => setNewContactRelation(e.target.value)} />
      </div>
      <div style={s.row}>
        <input style={s.inputSmall} placeholder="Phone" value={newContactPhone} onChange={e => setNewContactPhone(e.target.value)} />
        <input style={s.inputSmall} placeholder="Email" value={newContactEmail} onChange={e => setNewContactEmail(e.target.value)} />
        <button style={s.btn} onClick={addContact}>+</button>
      </div>

      <hr style={s.divider} />

      {/* ── Learned Facts ── */}
      <div style={s.sectionTitle}>🧠 Things JARVIS Knows About You</div>
      <div style={s.desc}>These are learned automatically during conversations. You can also add or remove them manually.</div>
      {facts.length === 0 && <div style={s.empty}>No facts yet — JARVIS will learn as you chat.</div>}
      {facts.map((f, i) => (
        <div key={i} style={s.card}>
          <div style={s.cardInfo}>
            <div style={s.cardMain}>{f.fact}</div>
            <div style={s.cardSub}>{f.source === 'conversation' ? '🤖 auto-learned' : '✍️ manual'} · {f.learned_at ? new Date(f.learned_at).toLocaleDateString() : ''}</div>
          </div>
          <button style={s.btnDanger} onClick={() => removeFact(f.fact)}>✕</button>
        </div>
      ))}
      <div style={s.row}>
        <input style={s.inputSmall} placeholder="Add a fact, e.g. 'I'm allergic to peanuts'" value={newFact} onChange={e => setNewFact(e.target.value)} onKeyDown={e => e.key === 'Enter' && addFact()} />
        <button style={s.btn} onClick={addFact}>+</button>
      </div>

      <hr style={s.divider} />

      {/* ── Work ── */}
      <div style={s.sectionTitle}>💼 Work</div>
      <div style={s.row}>
        <EditableField label="Job title" value={work.title} onSave={v => updateWorkField('title', v)} />
      </div>
      <div style={s.row}>
        <EditableField label="Company" value={work.company} onSave={v => updateWorkField('company', v)} />
      </div>
      <div style={s.row}>
        <EditableField label="Field" value={work.field} onSave={v => updateWorkField('field', v)} />
      </div>

      <hr style={s.divider} />

      {/* ── Routines ── */}
      <div style={s.sectionTitle}>🕐 Routines</div>
      {[
        ['wake_time', 'Wake time (e.g. 07:00)'],
        ['sleep_time', 'Sleep time (e.g. 23:00)'],
        ['work_hours', 'Work hours (e.g. 09:00-17:00)'],
        ['workout', 'Workout (e.g. gym 18:00 MWF)'],
        ['morning_routine', 'Morning routine'],
        ['commute', 'Commute'],
      ].map(([field, label]) => (
        <div key={field} style={s.row}>
          <EditableField label={label} value={routines[field]} onSave={v => updateRoutineField(field, v)} />
        </div>
      ))}

      <hr style={s.divider} />

      {/* ── Locations ── */}
      <div style={s.sectionTitle}>📍 Locations</div>
      <div style={s.row}>
        <EditableField label="Home address" value={locations.home} onSave={v => updateLocationField('home', v)} />
      </div>
      <div style={s.row}>
        <EditableField label="Office address" value={locations.office} onSave={v => updateLocationField('office', v)} />
      </div>
    </>
  );
}


/* ─────────────── Inline editable field ──────────────── */
function EditableField({ label, value, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || '');

  useEffect(() => { setDraft(value || ''); }, [value]);

  const save = () => {
    if (draft !== (value || '')) onSave(draft);
    setEditing(false);
  };

  if (editing) {
    return (
      <div style={{ flex: 1 }}>
        <input
          style={s.input}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false); }}
          onBlur={save}
          autoFocus
          placeholder={label}
        />
      </div>
    );
  }

  return (
    <div
      style={{ flex: 1, cursor: 'pointer', padding: '6px 10px', borderRadius: 6, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}
      onClick={() => setEditing(true)}
      title="Click to edit"
    >
      <div style={{ fontFamily: 'monospace', fontSize: 10, color: '#556677', marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: 'monospace', fontSize: 12, color: value ? '#c8d0d8' : '#334455' }}>
        {value || 'Not set — click to edit'}
      </div>
    </div>
  );
}


/* ─────────────────────────── SYSTEM TAB ──────────────────── */
const INTEGRATION_META = {
  gemini:        { label: 'Gemini AI',     icon: '🧠' },
  tts:           { label: 'Text-to-Speech',icon: '🔊' },
  whisper:       { label: 'Whisper STT',   icon: '🎤' },
  screen_vision: { label: 'Screen Vision', icon: '👁' },
  filesystem:    { label: 'File System',   icon: '📁' },
  terminal:      { label: 'Terminal',      icon: '💻' },
  browser:       { label: 'Browser Agent', icon: '🌐' },
};

const HEALTH_THEME = {
  ok:           { bg: 'rgba(0,200,100,0.06)', border: 'rgba(0,200,100,0.2)', color: '#55cc99', dot: '#00e676', label: 'Active' },
  failed:       { bg: 'rgba(255,60,60,0.06)', border: 'rgba(255,80,80,0.2)', color: '#ff8888', dot: '#ff4444', label: 'Error' },
  unconfigured: { bg: 'rgba(255,255,255,0.02)', border: 'rgba(255,255,255,0.05)', color: '#445566', dot: '#334455', label: 'Not configured' },
};

function SystemTab({ integrations = {} }) {
  // Filter out calendar and email
  const keys = Object.keys(INTEGRATION_META);

  return (
    <>
      <div style={s.subtitle}>
        Live health status of JARVIS subsystems. Green = active and verified.
      </div>
      {keys.map(key => {
        const meta = INTEGRATION_META[key];
        const info = integrations[key];
        let svcStatus = 'unconfigured';
        let tooltip = 'Not checked yet';
        if (info && typeof info === 'object') {
          svcStatus = info.status || 'unconfigured';
          tooltip = info.message || '';
        } else if (info === true) {
          svcStatus = 'ok';
          tooltip = 'Available';
        }
        const theme = HEALTH_THEME[svcStatus] || HEALTH_THEME.unconfigured;

        return (
          <div key={key} style={{
            ...s.card,
            background: theme.bg,
            borderColor: theme.border,
          }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: theme.dot, flexShrink: 0 }} />
            <div style={s.cardInfo}>
              <div style={{ ...s.cardMain, color: theme.color }}>
                {meta.icon} {meta.label}
              </div>
              <div style={s.cardSub}>{tooltip}</div>
            </div>
            <span style={{ fontFamily: 'monospace', fontSize: 9, color: theme.color, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {theme.label}
            </span>
          </div>
        );
      })}
    </>
  );
}


/* ─────────────────────── MAIN COMPONENT ─────────────────── */
export default function SettingsPanel({ open, onClose, integrations }) {
  const [activeTab, setActiveTab] = useState('preferences');

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ x: 390, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 390, opacity: 0 }}
          transition={{ type: 'spring', damping: 28, stiffness: 300 }}
          style={s.overlay}
        >
          {/* Header */}
          <div style={s.header}>
            <span style={s.title}>⚙ Settings</span>
            <button style={s.closeBtn} onClick={onClose}
              onMouseEnter={e => e.target.style.color = '#aab'}
              onMouseLeave={e => e.target.style.color = '#667'}
            >✕</button>
          </div>

          {/* Tabs */}
          <div style={s.tabs}>
            <button style={s.tab(activeTab === 'preferences')} onClick={() => setActiveTab('preferences')}>
              Preferences
            </button>
            <button style={s.tab(activeTab === 'profile')} onClick={() => setActiveTab('profile')}>
              My Profile
            </button>
            <button style={s.tab(activeTab === 'system')} onClick={() => setActiveTab('system')}>
              System
            </button>
          </div>

          {/* Tab content */}
          {activeTab === 'preferences' && <PreferencesTab />}
          {activeTab === 'profile' && <ProfileTab />}
          {activeTab === 'system' && <SystemTab integrations={integrations} />}

          <hr style={s.divider} />
          <div style={s.footer}>
            {activeTab === 'preferences'
              ? 'Changes are saved instantly and take effect on your next command.'
              : activeTab === 'profile'
              ? 'Profile info is injected into every AI conversation. JARVIS will also learn new facts automatically.'
              : 'Health checks run on startup. Re-check in the backend if something looks wrong.'}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
