# JARVIS — Personal AI Voice Assistant

A personal AI assistant with voice interface, screen vision, and system automation — powered by Claude.

![Stack](https://img.shields.io/badge/Claude-Sonnet_4-blueviolet) ![Stack](https://img.shields.io/badge/FastAPI-WebSocket-green) ![Stack](https://img.shields.io/badge/React-Vite-blue) ![Stack](https://img.shields.io/badge/Electron-Desktop-yellow)

---

## Quick Start

### 1. Clone & configure

```bash
cd Jarvis
cp .env.example .env   # or edit .env directly
# Fill in your API keys
```

### 2. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium     # for browser automation

# Run the server
python main.py
```

The backend starts at `ws://localhost:8000/ws` with a health check at `http://localhost:8000/health`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev          # Vite dev server at localhost:5173
```

### 4. Desktop App (optional)

```bash
cd frontend
npm run electron:dev  # Starts Vite + Electron together
```

Global shortcut: **Cmd+Shift+J** (macOS) / **Ctrl+Shift+J** (Win/Linux) to toggle the window.

---

## Architecture

```
User speaks → faster-whisper (local STT)
           → WebSocket → FastAPI
           → Claude (tool use loop)
           → Tools execute (screen, files, terminal, browser, calendar, email)
           → Claude responds
           → Fish Audio TTS (streaming)
           → Audio plays + transcript shown in UI
```

## Project Structure

```
jarvis/
├── backend/
│   ├── main.py              # FastAPI + WebSocket hub
│   ├── config.py            # Environment config
│   ├── audio/
│   │   ├── listener.py      # Mic → faster-whisper STT
│   │   └── speaker.py       # Fish Audio TTS streaming
│   ├── brain/
│   │   ├── claude.py        # Claude API + tool definitions + execution loop
│   │   └── memory.py        # Short-term session memory
│   └── tools/
│       ├── vision.py        # Screenshot + Claude vision
│       ├── filesystem.py    # File read/list/notes
│       ├── terminal.py      # Safe shell commands
│       ├── browser.py       # Playwright automation + search
│       ├── calendar.py      # Google Calendar (read-only)
│       └── email.py         # Gmail (read-only)
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main UI shell
│   │   ├── components/
│   │   │   ├── VoiceOrb.jsx     # Animated orb (listening/thinking/speaking)
│   │   │   ├── Transcript.jsx   # Live transcript display
│   │   │   ├── StatusBar.jsx    # Integration status chips
│   │   │   └── ContextPanel.jsx # Tool activity side panel
│   │   └── hooks/
│   │       └── useWebSocket.js  # WS connection + state management
│   └── electron/
│       ├── main.js          # Electron window
│       └── preload.js       # Safe IPC bridge
└── .env                     # API keys (not committed)
```

## Tools Available to Claude

| Tool | Description |
|------|-------------|
| `take_screenshot` | Captures screen, sends to Claude vision |
| `get_calendar_events` | Reads Google Calendar (next N days) |
| `get_emails` | Reads unread Gmail (filtered by sender) |
| `read_file` | Reads file contents |
| `list_directory` | Lists directory tree |
| `run_terminal_command` | Executes shell commands (with safety checks) |
| `open_browser` | Opens URL via Playwright |
| `browser_search` | Google search with result extraction |
| `create_note` | Saves markdown note to ~/Notes/ |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key |
| `FISH_AUDIO_API_KEY` | ✅ | Fish Audio TTS key |
| `FISH_AUDIO_VOICE_ID` | ✅ | Voice ID for TTS |
| `GOOGLE_CLIENT_ID` | Optional | For Calendar/Gmail |
| `GOOGLE_CLIENT_SECRET` | Optional | For Calendar/Gmail |
| `JARVIS_USERNAME` | Optional | Display name (default: User) |
| `WHISPER_MODEL` | Optional | Whisper model size (default: base.en) |

## Safety

- Terminal commands are sanitized — `rm`, `sudo`, `shutdown`, etc. are blocked
- Gmail is strictly read-only
- Screenshots only captured on explicit request or when Claude decides it's contextually needed
- Session memory resets on restart (no persistent storage in v1)
- All AI inference goes through Claude — no other LLM

---

Built with 🤖 by JARVIS
