"""
JARVIS — FastAPI Entry Point & WebSocket Hub

This is the central nervous system. It:
  1. Hosts the FastAPI HTTP + WebSocket server
  2. Manages bidirectional real-time comms with the React frontend
  3. Orchestrates the flow: mic → STT → Claude → tools → TTS → UI
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import platform
import subprocess
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import cfg
from preferences import get_preferences, set_preferences, get_schema as get_pref_schema
from user_profile import get_profile, update_profile, learn_fact as profile_learn_fact, add_email_account as profile_add_email, add_contact as profile_add_contact, remove_fact as profile_remove_fact
from brain.gemini import GeminiBrain
from brain.memory import SessionMemory
from audio.listener import WhisperListener
from audio.speaker import TTSSpeaker
from clients.telegram_client import TelegramClient
from health_check import check_all
from tools.scheduler import _active_reminders
from tools.screen_watcher import TEMPLATES_DIR, watch_for, bootstrap_templates

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-18s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jarvis.main")


# ── Message Types ─────────────────────────────────────────────
class MsgType(str, Enum):
    """All WebSocket message types between frontend ↔ backend."""
    # Frontend → Backend
    START_LISTENING = "start_listening"
    STOP_LISTENING = "stop_listening"
    TEXT_INPUT = "text_input"           # typed query instead of voice
    CANCEL = "cancel"

    # Backend → Frontend
    LISTENING = "listening"             # mic is active
    TRANSCRIBING = "transcribing"       # Whisper is processing
    TRANSCRIPT = "transcript"           # final STT result
    THINKING = "thinking"              # Claude is processing
    TOOL_CALL = "tool_call"            # Claude called a tool
    TOOL_RESULT = "tool_result"        # tool returned a result
    BROWSER_STEP = "browser_step"      # browser agent progress update
    RESPONSE_TEXT = "response_text"    # Claude's text response (streamed chunks)
    RESPONSE_DONE = "response_done"    # full response complete
    SPEAKING = "speaking"              # TTS audio playing
    TTS_AUDIO = "tts_audio"           # audio chunk (base64)
    TTS_DONE = "tts_done"             # TTS finished
    STOP_TTS = "stop_tts"             # interrupt TTS playback (barge-in)
    ERROR = "error"
    STATUS = "status"                  # system status updates


# ── Connection Manager ────────────────────────────────────────
class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        log.info(f"Client connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        log.info(f"Client disconnected. Total: {len(self.active)}")

    async def broadcast(self, msg_type: MsgType, data: dict[str, Any] | None = None):
        payload = json.dumps({"type": msg_type.value, "data": data or {}, "ts": _now()})
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                pass

    async def send(self, ws: WebSocket, msg_type: MsgType, data: dict[str, Any] | None = None) -> bool:
        """Send a message. Returns False if the socket is dead."""
        payload = json.dumps({"type": msg_type.value, "data": data or {}, "ts": _now()})
        try:
            await ws.send_text(payload)
            return True
        except Exception:
            return False


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


# ── Globals ───────────────────────────────────────────────────
manager = ConnectionManager()
brain = GeminiBrain()
memory = SessionMemory()
listener = WhisperListener()
speaker = TTSSpeaker()
telegram = TelegramClient(brain, memory, speaker)

# Track active processing so we can cancel
_active_tasks: dict[int, asyncio.Task] = {}
_listening_tasks: dict[int, asyncio.Task] = {}

# Sleep prevention process (macOS only)
_caffeinate_process: subprocess.Popen | None = None

# Startup health check results: {service: {status, message}}
_health_results: dict[str, dict[str, str]] = {}


# ── Lifespan ──────────────────────────────────────────────────
def _start_sleep_prevention():
    """Start caffeinate process on macOS to prevent sleep when lid is closed."""
    global _caffeinate_process
    if platform.system() == "Darwin":  # macOS only
        try:
            _caffeinate_process = subprocess.Popen(
                ["caffeinate", "-d", "-i", "-s", "-u"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            log.info("💤 Sleep prevention enabled (caffeinate)")
        except Exception as e:
            log.warning(f"⚠ Could not start caffeinate: {e}")


def _stop_sleep_prevention():
    """Kill the caffeinate process."""
    global _caffeinate_process
    if _caffeinate_process is not None:
        try:
            _caffeinate_process.terminate()
            _caffeinate_process.wait(timeout=2)
            log.info("💤 Sleep prevention disabled")
        except Exception as e:
            log.warning(f"⚠ Error stopping caffeinate: {e}")
        finally:
            _caffeinate_process = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    global _health_results

    # Start sleep prevention on macOS
    _start_sleep_prevention()

    log.info("─" * 50)
    log.info("🔍 Running startup health checks...")
    log.info("─" * 50)

    _health_results = await check_all()

    # Request macOS permissions for OpenCV screen automation
    from tools.app_control import check_and_request_permissions
    await check_and_request_permissions()

    # Pretty-print results to terminal
    status_icons = {"ok": "✅", "failed": "❌", "unconfigured": "⬜"}
    for service, info in _health_results.items():
        icon = status_icons.get(info["status"], "❓")
        log.info(f"  {icon} {service:<15} {info['message']}")

    # Summary
    ok_count = sum(1 for v in _health_results.values() if v["status"] == "ok")
    fail_count = sum(1 for v in _health_results.values() if v["status"] == "failed")
    unconf_count = sum(1 for v in _health_results.values() if v["status"] == "unconfigured")
    total = len(_health_results)

    log.info("─" * 50)
    if fail_count:
        log.warning(f"⚠ Health: {ok_count}/{total} OK, {fail_count} FAILED, {unconf_count} not configured")
    else:
        log.info(f"✓ Health: {ok_count}/{total} OK, {unconf_count} not configured")

    log.info(f"🧠 Gemini model: {cfg.GEMINI_MODEL}")
    log.info(f"🎤 Whisper model: {cfg.WHISPER_MODEL}")
    log.info(f"🚀 JARVIS is online — ws://localhost:{cfg.PORT}/ws")

    # Show local IP for Android clients
    _local_ip = _get_local_ip()
    log.info(f"📱 Android endpoint: ws://{_local_ip}:{cfg.PORT}/ws/android")

    # Start Screen Watchers for auto-click rules
    from tools.screen_watcher import bootstrap_templates
    bootstrap_templates()

    for rule in getattr(cfg, 'AUTO_CLICK_RULES', []):
        if rule.get('action') == 'click' and not rule.get('confirm'):
            watch_for(rule['watch'], auto_click=True)
            log.info(f"👁️  Auto-watching screen for: {rule['watch']}")

    # Start Telegram bot — wire desktop broadcast so Telegram events appear on desktop
    async def _telegram_broadcast(msg_type_str: str, data: dict):
        """Forward Telegram pipeline events to all connected desktop WebSocket clients."""
        try:
            msg_type = MsgType(msg_type_str)
            await manager.broadcast(msg_type, data)
        except Exception:
            pass

    telegram._desktop_broadcast = _telegram_broadcast
    await telegram.start()

    yield  # ── app is running ──

    # Cleanup
    _stop_sleep_prevention()
    await telegram.stop()
    try:
        from tools.browser import close_browser
        await close_browser()
    except Exception:
        pass
    for task in _active_tasks.values():
        task.cancel()
    log.info("JARVIS shutting down.")


# ── App ───────────────────────────────────────────────────────
app = FastAPI(title="JARVIS", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ──────────────────────────────────────────────
@app.get("/health")
async def health():
    ok = all(v["status"] == "ok" for k, v in _health_results.items() if k in ("gemini",))
    return {
        "status": "online" if ok else "degraded",
        "model": cfg.GEMINI_MODEL,
        "whisper": cfg.WHISPER_MODEL,
        "services": _health_results,
        "ts": _now(),
    }


@app.post("/health/recheck")
async def recheck_health():
    """Re-run all health checks (e.g. after updating .env)."""
    global _health_results
    _health_results = await check_all()
    return {"services": _health_results, "ts": _now()}


# ── Preferences API ───────────────────────────────────────────
@app.get("/preferences")
async def api_get_preferences():
    """Return current user preferences."""
    return {"preferences": get_preferences(), "ts": _now()}


@app.get("/preferences/schema")
async def api_get_preferences_schema():
    """Return the full schema so the frontend can build the settings UI."""
    return {"schema": get_pref_schema(), "ts": _now()}


@app.put("/preferences")
async def api_set_preferences(request: Request):
    """Update one or more preferences. Body: {"preferences": {"key": "value", ...}}"""
    body = await request.json()
    updates = body.get("preferences", {})
    updated = set_preferences(updates)
    # Rebuild the system prompt so the AI picks up the new defaults
    brain.system_prompt = brain._build_system_prompt()
    return {"preferences": updated, "ts": _now()}


# ── Context API ───────────────────────────────────────────────
@app.get("/context_data")
async def api_get_context_data():
    """Return reminders and notes for holographic display."""
    profile = get_profile()
    notes = profile.get("facts", [])
    
    # Filter out fired reminders or format them
    reminders = [r for r in _active_reminders if not r.get("fired", False)]
    
    return {
        "notes": notes,
        "reminders": reminders,
        "ts": _now()
    }

# ── User Profile API ─────────────────────────────────────────
@app.get("/profile")
async def api_get_profile():
    """Return the full user profile."""
    return {"profile": get_profile(), "ts": _now()}


@app.put("/profile")
async def api_update_profile(request: Request):
    """Deep-update the user profile. Body: {"profile": {...partial updates...}}"""
    body = await request.json()
    updates = body.get("profile", {})
    updated = update_profile(updates)
    # Rebuild system prompt so the AI sees the new profile
    brain.system_prompt = brain._build_system_prompt()
    return {"profile": updated, "ts": _now()}


@app.post("/profile/email")
async def api_add_email(request: Request):
    """Add an email account. Body: {"address": "...", "label": "...", "default": true/false}"""
    body = await request.json()
    profile = profile_add_email(
        address=body["address"],
        default=body.get("default", False),
        label=body.get("label", ""),
    )
    brain.system_prompt = brain._build_system_prompt()
    return {"profile": profile, "ts": _now()}


@app.post("/profile/contact")
async def api_add_contact(request: Request):
    """Add a contact. Body: {"name": "...", "relation": "...", "phone": "...", "email": "...", "notes": "..."}"""
    body = await request.json()
    profile = profile_add_contact(
        name=body["name"],
        relation=body.get("relation", ""),
        phone=body.get("phone", ""),
        email=body.get("email", ""),
        notes=body.get("notes", ""),
    )
    brain.system_prompt = brain._build_system_prompt()
    return {"profile": profile, "ts": _now()}


@app.post("/profile/fact")
async def api_add_fact(request: Request):
    """Add a learned fact. Body: {"fact": "..."}"""
    body = await request.json()
    profile = profile_learn_fact(body["fact"], source="manual")
    brain.system_prompt = brain._build_system_prompt()
    return {"profile": profile, "ts": _now()}


@app.delete("/profile/fact")
async def api_remove_fact(request: Request):
    """Remove a fact. Body: {"fact": "..."}"""
    body = await request.json()
    profile = profile_remove_fact(body["fact"])
    brain.system_prompt = brain._build_system_prompt()
    return {"profile": profile, "ts": _now()}


# ── WebSocket Endpoint ────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)

    # Send initial status with real health check results
    await manager.send(ws, MsgType.STATUS, {
        "message": "JARVIS online",
        "username": cfg.USERNAME,
        "integrations": _build_integration_status(),
    })

    # Start a heartbeat task to keep the connection alive
    async def _heartbeat():
        """Send periodic pings to keep WebSocket alive when lid is closed."""
        try:
            while True:
                await asyncio.sleep(30)  # Ping every 30 seconds
                await manager.send(ws, MsgType.STATUS, {"ping": True})
        except Exception:
            pass

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")
            data = msg.get("data", {})

            log.info(f"← {msg_type}")

            if msg_type == MsgType.START_LISTENING.value:
                await _handle_start_listening(ws)

            elif msg_type == MsgType.STOP_LISTENING.value:
                await _handle_stop_listening(ws)

            elif msg_type == MsgType.TEXT_INPUT.value:
                text = data.get("text", "").strip()
                if text:
                    # Cancel any active query/TTS (barge-in via text)
                    active = _active_tasks.pop(id(ws), None)
                    if active:
                        active.cancel()
                    await manager.send(ws, MsgType.STOP_TTS, {})
                    task = asyncio.create_task(_process_query(ws, text))
                    _active_tasks[id(ws)] = task

            elif msg_type == MsgType.CANCEL.value:
                task = _active_tasks.pop(id(ws), None)
                if task:
                    task.cancel()
                    log.info("Cancelled active task")
                listener.stop()

    except WebSocketDisconnect:
        manager.disconnect(ws)
        _active_tasks.pop(id(ws), None)
        task = _listening_tasks.pop(id(ws), None)
        if task:
            task.cancel()
        listener.stop()
    except Exception as e:
        log.error(f"WebSocket error: {e}\n{traceback.format_exc()}")
        await manager.send(ws, MsgType.ERROR, {"message": str(e)})
        manager.disconnect(ws)
    finally:
        heartbeat_task.cancel()


# ── Voice Flow ────────────────────────────────────────────────
async def _handle_start_listening(ws: WebSocket):
    """Start mic capture → Whisper transcription (non-blocking).

    Runs the full flow as a background task so the WebSocket message
    loop stays responsive and can process stop_listening immediately.
    Supports barge-in: cancels any active query/TTS task first.
    """
    # ── Barge-in: cancel active query/TTS task ──
    active = _active_tasks.pop(id(ws), None)
    if active:
        active.cancel()
        log.info("🛑 Barge-in: cancelled active query/TTS task")

    # Tell frontend to stop any audio playback immediately
    await manager.send(ws, MsgType.STOP_TTS, {})

    # Cancel a previous listening flow if still running
    prev = _listening_tasks.pop(id(ws), None)
    if prev:
        prev.cancel()
        listener.stop()

    task = asyncio.create_task(_listening_flow(ws))
    _listening_tasks[id(ws)] = task


async def _listening_flow(ws: WebSocket):
    """Record → transcribe → process query (runs as a task)."""
    await manager.send(ws, MsgType.LISTENING, {"active": True})

    try:
        # 1. Record audio in a thread (respects listener.stop() signal)
        audio = await asyncio.to_thread(listener.record)

        if audio is None or len(audio) == 0:
            await manager.send(ws, MsgType.LISTENING, {"active": False})
            await manager.send(ws, MsgType.TRANSCRIPT, {"text": "", "empty": True})
            return

        # 2. Tell the UI recording is done — now transcribing
        await manager.send(ws, MsgType.TRANSCRIBING, {})

        # 3. Transcribe in a thread
        transcript = await asyncio.to_thread(listener.transcribe, audio)

        if not transcript:
            await manager.send(ws, MsgType.LISTENING, {"active": False})
            await manager.send(ws, MsgType.TRANSCRIPT, {"text": "", "empty": True})
            return

        await manager.send(ws, MsgType.TRANSCRIPT, {"text": transcript})

        # 4. Process the transcribed query
        task = asyncio.create_task(_process_query(ws, transcript))
        _active_tasks[id(ws)] = task

    except asyncio.CancelledError:
        log.info("Listening flow cancelled")
        await manager.send(ws, MsgType.LISTENING, {"active": False})
    except Exception as e:
        log.error(f"Listening error: {e}")
        await manager.send(ws, MsgType.ERROR, {"message": f"Listening error: {e}"})
        await manager.send(ws, MsgType.LISTENING, {"active": False})
    finally:
        _listening_tasks.pop(id(ws), None)


async def _handle_stop_listening(ws: WebSocket):
    """Force-stop the microphone and cancel any listening flow."""
    listener.stop()
    task = _listening_tasks.pop(id(ws), None)
    if task:
        task.cancel()
    await manager.send(ws, MsgType.LISTENING, {"active": False})


# ── Query Processing Pipeline ─────────────────────────────────
async def _process_query(ws: WebSocket, user_text: str):
    """
    The main pipeline:
      user_text → Claude (with tools) → TTS → UI
    """
    log.info(f"Processing: {user_text[:80]}...")

    try:
        # 1. Tell UI we're thinking
        await manager.send(ws, MsgType.THINKING, {"query": user_text})

        # 2. Add user message to memory
        memory.add_user_message(user_text)

        # 3. Run Gemini with tool loop
        # Set up browser step callback to send progress to frontend
        async def on_browser_step(summary, info, step_num):
            await manager.send(ws, MsgType.BROWSER_STEP, {
                "step": step_num,
                "summary": summary,
                "url": info.get("url", ""),
                "actions": info.get("actions", []),
            })

        full_response = ""
        async for event in brain.chat(memory.get_messages(), on_browser_step=on_browser_step):
            if event["type"] == "tool_call":
                await manager.send(ws, MsgType.TOOL_CALL, {
                    "tool": event["tool"],
                    "input": event["input"],
                })

            elif event["type"] == "tool_result":
                await manager.send(ws, MsgType.TOOL_RESULT, {
                    "tool": event["tool"],
                    "summary": _summarize_tool_result(event["result"]),
                })

            elif event["type"] == "text_delta":
                chunk = event["text"]
                full_response += chunk
                await manager.send(ws, MsgType.RESPONSE_TEXT, {"chunk": chunk})

            elif event["type"] == "text_done":
                full_response = event["text"]

        # 4. Save assistant response to memory
        memory.add_assistant_message(full_response)

        await manager.send(ws, MsgType.RESPONSE_DONE, {"text": full_response})

        # 5. TTS — stream audio to frontend
        if full_response.strip():
            await manager.send(ws, MsgType.SPEAKING, {"active": True})
            try:
                async for audio_chunk in speaker.synthesize(full_response):
                    b64 = base64.b64encode(audio_chunk).decode("utf-8")
                    await manager.send(ws, MsgType.TTS_AUDIO, {"audio": b64})
                await manager.send(ws, MsgType.TTS_DONE, {})
            except Exception as e:
                log.error(f"TTS error: {e}")
                await manager.send(ws, MsgType.TTS_DONE, {"error": str(e)})

    except asyncio.CancelledError:
        log.info("Query processing cancelled")
        await manager.send(ws, MsgType.RESPONSE_DONE, {"text": "", "cancelled": True})
    except Exception as e:
        log.error(f"Pipeline error: {e}\n{traceback.format_exc()}")
        # Send a clean, user-friendly error message
        err_msg = _friendly_error(e)
        await manager.send(ws, MsgType.ERROR, {"message": err_msg})
        await manager.send(ws, MsgType.RESPONSE_DONE, {"text": "", "error": True})
    finally:
        _active_tasks.pop(id(ws), None)


# ── Helpers ───────────────────────────────────────────────────
def _friendly_error(e: Exception) -> str:
    """Convert exceptions to clean UI-displayable messages."""
    msg = str(e)
    if "api_key" in msg.lower() or "api key" in msg.lower() or "invalid" in msg.lower():
        return "Gemini API key is invalid. Check GEMINI_API_KEY in your .env file."
    if "rate_limit" in msg.lower() or "resource_exhausted" in msg.lower() or "429" in msg:
        return "Rate limited by Gemini. Wait a moment and try again."
    if "overloaded" in msg.lower() or "503" in msg:
        return "Gemini is overloaded right now. Try again in a few seconds."
    if "quota" in msg.lower() or "billing" in msg.lower():
        return "Gemini quota exceeded. Check your Google Cloud billing."
    if "connection" in msg.lower() or "timeout" in msg.lower():
        return "Could not reach Gemini API. Check your internet connection."
    # Fallback: truncate the raw message
    if len(msg) > 150:
        return msg[:150] + "…"
    return msg


def _build_integration_status() -> dict[str, dict]:
    """
    Build integration status from real health check results.
    Returns {service: {status, message}} for each integration.
    """
    return {
        service: {
            "status": info["status"],    # "ok" | "failed" | "unconfigured"
            "message": info["message"],
        }
        for service, info in _health_results.items()
    }


def _summarize_tool_result(result: Any) -> str:
    """Create a short UI-friendly summary of a tool result."""
    if isinstance(result, str):
        if len(result) > 200:
            return result[:200] + "…"
        return result
    if isinstance(result, dict):
        return json.dumps(result, default=str)[:200]
    return str(result)[:200]


# ── Utility ───────────────────────────────────────────────────
def _get_local_ip() -> str:
    """Get the machine's local WiFi IP for Android clients."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── Android WebSocket Endpoint ────────────────────────────────
# Protocol:
#   Binary frames  → raw PCM audio (16kHz, mono, int16) from Android mic
#   Text frames    → JSON commands: {"type": "start_listening"} etc.
#   Backend sends text frames (JSON) for status/transcript/response
#   Backend sends binary frames for TTS audio (raw PCM int16)

ANDROID_SAMPLE_RATE = 16000
ANDROID_PCM_DTYPE = np.int16

# Per-connection Android state
_android_audio_buffers: dict[int, list[bytes]] = {}
_android_tasks: dict[int, asyncio.Task] = {}


async def _android_send_json(ws: WebSocket, msg_type: str, content: str = "", **extra) -> bool:
    """Send a JSON text frame to the Android client."""
    payload = json.dumps({"type": msg_type, "content": content, **extra, "ts": _now()})
    try:
        await ws.send_text(payload)
        return True
    except Exception:
        return False


@app.websocket("/ws/android")
async def android_ws_endpoint(ws: WebSocket):
    """
    WebSocket endpoint for Android client.

    Accepts:
      - Binary frames: raw PCM audio chunks (while recording)
      - Text frames: JSON commands (start_listening, stop_listening, text_input)

    Sends:
      - Text frames: JSON status/transcript/response/tool_active messages
      - Binary frames: raw PCM TTS audio
    """
    await ws.accept()
    cid = id(ws)
    _android_audio_buffers[cid] = []
    is_recording = False

    log.info(f"📱 Android client connected (cid={cid})")
    await _android_send_json(ws, "status", f"JARVIS online. Welcome, {cfg.USERNAME}.")

    # Start a heartbeat task to keep the connection alive
    async def _heartbeat():
        """Send periodic pings to keep WebSocket alive when lid is closed."""
        try:
            while True:
                await asyncio.sleep(30)  # Ping every 30 seconds
                await _android_send_json(ws, "ping", "")
        except Exception:
            pass

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            msg = await ws.receive()

            # ── Binary frame: PCM audio chunk ──
            if "bytes" in msg and msg["bytes"]:
                if is_recording:
                    _android_audio_buffers[cid].append(msg["bytes"])

            # ── Text frame: JSON command ──
            elif "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                cmd = data.get("type", "")

                if cmd == "start_listening":
                    # Barge-in: cancel active query/TTS task
                    active = _android_tasks.pop(cid, None)
                    if active:
                        active.cancel()
                        log.info("📱 Barge-in: cancelled active Android task")
                    is_recording = True
                    _android_audio_buffers[cid] = []
                    await _android_send_json(ws, "status", "listening")
                    log.info("📱 Android: start_listening")

                elif cmd == "stop_listening":
                    is_recording = False
                    log.info("📱 Android: stop_listening")

                    # Collect buffered audio
                    raw_chunks = _android_audio_buffers.pop(cid, [])
                    _android_audio_buffers[cid] = []

                    if raw_chunks:
                        pcm_data = b"".join(raw_chunks)
                        audio_np = np.frombuffer(pcm_data, dtype=ANDROID_PCM_DTYPE)
                        log.info(f"📱 Received {len(audio_np) / ANDROID_SAMPLE_RATE:.1f}s of audio")

                        # Transcribe
                        await _android_send_json(ws, "status", "transcribing")
                        transcript = await asyncio.to_thread(listener.transcribe, audio_np)

                        if transcript:
                            await _android_send_json(ws, "transcript", transcript)
                            # Process through brain
                            task = asyncio.create_task(
                                _android_process_query(ws, transcript)
                            )
                            _android_tasks[cid] = task
                        else:
                            await _android_send_json(ws, "transcript", "(no speech detected)")
                            await _android_send_json(ws, "status", "idle")
                    else:
                        await _android_send_json(ws, "status", "idle")

                elif cmd == "text_input":
                    text = data.get("text", "").strip()
                    if text:
                        # Attach GPS coords as context if provided
                        lat = data.get("lat")
                        lon = data.get("lon")
                        if lat is not None and lon is not None:
                            text = f"[User location: {lat:.6f}, {lon:.6f}] {text}"
                        log.info(f"📱 Android text: \"{text[:80]}\"")
                        
                        # Do NOT send "transcript" event here for text input, because the Android 
                        # app already adds typed text locally to the chat UI. Sending it again 
                        # causes duplicate messages.
                        
                        await _android_send_json(ws, "status", "thinking")
                        
                        task = asyncio.create_task(
                            _android_process_query(ws, text)
                        )
                        _android_tasks[cid] = task

                elif cmd == "cancel":
                    t = _android_tasks.pop(cid, None)
                    if t:
                        t.cancel()
                    await _android_send_json(ws, "status", "idle")

    except WebSocketDisconnect:
        log.info(f"📱 Android client disconnected (cid={cid})")
    except Exception as e:
        log.error(f"📱 Android WS error: {e}\n{traceback.format_exc()}")
    finally:
        heartbeat_task.cancel()
        _android_audio_buffers.pop(cid, None)
        # Don't immediately cancel the task — let it complete
        # Only cancel if it's still running 10 seconds later
        t = _android_tasks.pop(cid, None)
        if t and not t.done():
            try:
                await asyncio.wait_for(asyncio.shield(t), timeout=10)
            except asyncio.TimeoutError:
                t.cancel()
                log.info(f"📱 Force cancelled Android task (cid={cid}) after timeout")
            except Exception:
                pass


async def _android_process_query(ws: WebSocket, user_text: str):
    """Process a query from Android — same brain pipeline, different output format."""
    try:
        await _android_send_json(ws, "status", "thinking")
        memory.add_user_message(user_text)

        full_response = ""
        async for event in brain.chat(memory.get_messages()):
            if event["type"] == "tool_call":
                await _android_send_json(
                    ws, "tool_active",
                    f"Using {event['tool']}...",
                    tool=event["tool"],
                )
            elif event["type"] == "tool_result":
                # Only send screenshots back to Android if the user explicitly asked about the screen
                screenshot_b64 = event.get("screenshot_b64")
                if screenshot_b64:
                    text_lower = user_text.lower()
                    if "screenshot" in text_lower or "what's on" in text_lower or "what is on" in text_lower or "see" in text_lower or "look" in text_lower:
                        await _android_send_json(ws, "image", screenshot_b64)
            elif event["type"] == "text_delta":
                full_response += event["text"]
            elif event["type"] == "text_done":
                full_response = event["text"]

        memory.add_assistant_message(full_response)
        await _android_send_json(ws, "response", full_response)

        # Stream TTS as binary PCM frames
        if full_response.strip():
            await _android_send_json(ws, "status", "speaking")
            try:
                async for audio_chunk in speaker.synthesize(full_response):
                    # Send MP3 audio as binary frames
                    await ws.send_bytes(audio_chunk)
                await _android_send_json(ws, "tts_done", "")
            except Exception as e:
                log.error(f"📱 Android TTS error: {e}")

        await _android_send_json(ws, "status", "idle")

    except asyncio.CancelledError:
        await _android_send_json(ws, "status", "idle")
    except Exception as e:
        log.error(f"📱 Android pipeline error: {e}")
        await _android_send_json(ws, "error", str(e)[:200])
        await _android_send_json(ws, "status", "idle")


# ── Discovery endpoint for Android ───────────────────────────
@app.get("/discover")
async def discover():
    """Android app can hit this to verify the backend is reachable."""
    return {
        "name": "JARVIS",
        "version": "1.0.0",
        "ws_endpoint": "/ws/android",
        "sample_rate": ANDROID_SAMPLE_RATE,
        "ip": _get_local_ip(),
    }


# ── Run ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=cfg.HOST,
        port=cfg.PORT,
        reload=True,
        log_level="info",
    )
