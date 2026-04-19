"""
JARVIS — Telegram Remote Client

Lets you send commands to JARVIS from anywhere via Telegram.
Supports text, voice notes, screenshots, proactive notifications.

Security: only processes messages from TELEGRAM_CHAT_ID (whitelist).
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from collections import deque
from pathlib import Path
from typing import Optional

from config import cfg

log = logging.getLogger("jarvis.telegram")

# Rate limit: max commands per minute
_MAX_COMMANDS_PER_MINUTE = 10
_command_timestamps: deque[float] = deque(maxlen=_MAX_COMMANDS_PER_MINUTE)

# Reference to the running Application (set on start)
_app = None

# Telegram max message length
_TG_MAX_LEN = 4096


def _is_rate_limited() -> bool:
    now = time.time()
    while _command_timestamps and now - _command_timestamps[0] > 60:
        _command_timestamps.popleft()
    return len(_command_timestamps) >= _MAX_COMMANDS_PER_MINUTE


def _split_message(text: str, max_len: int = _TG_MAX_LEN) -> list[str]:
    """Split long text into Telegram-safe chunks at paragraph boundaries."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Find last newline before limit
        idx = text.rfind("\n", 0, max_len)
        if idx == -1:
            idx = text.rfind(". ", 0, max_len)
        if idx == -1:
            idx = max_len
        chunks.append(text[: idx + 1])
        text = text[idx + 1 :]
    return chunks


class TelegramClient:
    """Telegram bot that routes messages through the JARVIS brain pipeline."""

    def __init__(self, brain, memory, speaker):
        self.brain = brain
        self.memory = memory
        self.speaker = speaker
        self._application = None
        self._desktop_broadcast = None  # set by main.py to push events to desktop

    async def start(self):
        """Start the Telegram bot (runs in background)."""
        if not cfg.TELEGRAM_BOT_TOKEN:
            log.info("⬜ Telegram: no TELEGRAM_BOT_TOKEN — skipping")
            return

        try:
            from telegram import Update, Bot
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            log.error("❌ python-telegram-bot not installed: pip install python-telegram-bot")
            return

        global _app

        self._application = (
            Application.builder()
            .token(cfg.TELEGRAM_BOT_TOKEN)
            .build()
        )
        _app = self._application

        # Register handlers
        self._application.add_handler(CommandHandler("start", self._cmd_start))
        self._application.add_handler(CommandHandler("status", self._cmd_status))
        self._application.add_handler(CommandHandler("screenshot", self._cmd_screenshot))
        self._application.add_handler(CommandHandler("briefing", self._cmd_briefing))
        # Catch-all for natural language
        self._application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        try:
            await self._application.initialize()
            await self._application.start()
            await self._application.updater.start_polling(drop_pending_updates=True)
            log.info("💬 Telegram bot started")
        except Exception as e:
            log.error(f"❌ Telegram bot failed to start: {e}")
            log.error("   Check your TELEGRAM_BOT_TOKEN in .env")
            self._application = None
            _app = None
            return

    async def stop(self):
        if self._application:
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()
            log.info("Telegram bot stopped")

    # ── Security ──────────────────────────────────────────────
    def _authorized(self, update) -> bool:
        chat_id = str(update.effective_chat.id)
        if not cfg.TELEGRAM_CHAT_ID:
            # First message sets the chat ID — log it so user can copy
            log.warning(
                f"⚠️  TELEGRAM_CHAT_ID not set. Your chat ID is: {chat_id}\n"
                f"   Add TELEGRAM_CHAT_ID={chat_id} to your .env file."
            )
            return True  # Allow first contact

        if chat_id != cfg.TELEGRAM_CHAT_ID:
            log.warning(f"🚫 Unauthorized Telegram user: {chat_id}")
            return False
        return True

    # ── Command Handlers ──────────────────────────────────────
    async def _cmd_start(self, update, context):
        if not self._authorized(update):
            return
        await update.message.reply_text(
            "🤖 JARVIS online. Ready.\n\n"
            "Send me any message and I'll process it.\n"
            "Commands:\n"
            "/status — system status\n"
            "/screenshot — capture screen\n"
            "/briefing — daily briefing"
        )

    async def _cmd_status(self, update, context):
        if not self._authorized(update):
            return
        import platform
        import psutil

        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        text = (
            f"📊 **JARVIS Status**\n\n"
            f"💻 Host: {platform.node()}\n"
            f"🧠 Model: {cfg.GEMINI_MODEL}\n"
            f"🎤 Whisper: {cfg.WHISPER_MODEL}\n"
            f"📈 CPU: {cpu}%\n"
            f"🧮 RAM: {mem.percent}% ({mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB)\n"
            f"💾 Disk: {disk.percent}% used\n"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def _cmd_screenshot(self, update, context):
        if not self._authorized(update):
            return
        try:
            from tools.vision import take_screenshot

            result = await take_screenshot()
            if isinstance(result, list) and result:
                # take_screenshot returns [{"type": "image", "source": {"data": b64, ...}}]
                for item in result:
                    b64_data = None
                    if isinstance(item, dict):
                        b64_data = item.get("source", {}).get("data")
                    if b64_data:
                        img_bytes = base64.b64decode(b64_data)
                        await update.message.reply_photo(
                            photo=io.BytesIO(img_bytes),
                            caption="📸 Current screen",
                        )
                        return
            await update.message.reply_text("📸 Screenshot captured (no image data)")
        except Exception as e:
            await update.message.reply_text(f"❌ Screenshot error: {e}")

    async def _cmd_briefing(self, update, context):
        if not self._authorized(update):
            return
        await update.message.reply_text("🔄 Generating briefing...")
        await self._process_and_reply(
            update,
            "Give me a brief daily briefing: upcoming calendar events, unread emails summary, weather.",
        )

    # ── Natural Language Handler ──────────────────────────────
    async def _handle_message(self, update, context):
        if not self._authorized(update):
            return

        if _is_rate_limited():
            await update.message.reply_text("⏳ Rate limited. Wait a moment.")
            return

        _command_timestamps.append(time.time())
        user_text = update.message.text.strip()
        if not user_text:
            return

        log.info(f"💬 Telegram: \"{user_text[:80]}\"")
        await self._process_and_reply(update, user_text)

    async def _process_and_reply(self, update, user_text: str):
        """Route text through the brain pipeline and send response.
        Also broadcasts events to desktop WebSocket clients so the UI stays in sync.
        """
        bc = self._desktop_broadcast  # shorthand

        try:
            self.memory.add_user_message(user_text)
            status_msg = await update.message.reply_text("⏳ Working on it...")

            # Notify desktop: Telegram query incoming
            if bc:
                await bc("transcript", {"text": f"📱 [Telegram] {user_text}"})
                await bc("thinking", {"query": user_text})

            full_response = ""
            async for event in self.brain.chat(self.memory.get_messages()):
                if event["type"] == "tool_call":
                    try:
                        await status_msg.edit_text(f"⏳ Using {event['tool']}...")
                    except Exception:
                        pass
                    if bc:
                        await bc("tool_call", {
                            "tool": event["tool"],
                            "input": event["input"],
                        })
                elif event["type"] == "tool_result":
                    try:
                        await status_msg.edit_text(f"⏳ Analyzing results from {event['tool']}...")
                    except Exception:
                        pass
                    if bc:
                        result = event.get("result", "")
                        summary = str(result)[:300] if result else ""
                        await bc("tool_result", {
                            "tool": event["tool"],
                            "summary": summary,
                        })
                    # Send screenshots to Telegram so user can see what JARVIS sees if explicitly asked
                    screenshot_b64 = event.get("screenshot_b64")
                    if screenshot_b64:
                        text_lower = user_text.lower()
                        if "screenshot" in text_lower or "what's on" in text_lower or "what is on" in text_lower or "see" in text_lower or "look" in text_lower:
                            try:
                                img_bytes = base64.b64decode(screenshot_b64)
                                await update.message.reply_photo(
                                    photo=io.BytesIO(img_bytes),
                                    caption=f"📸 Screenshot ({event.get('tool', 'vision')})",
                                )
                            except Exception as e:
                                log.warning(f"Failed to send screenshot to Telegram: {e}")
                elif event["type"] == "text_delta":
                    full_response += event["text"]
                    if bc:
                        await bc("response_text", {"chunk": event["text"]})
                elif event["type"] == "text_done":
                    full_response = event["text"]

            self.memory.add_assistant_message(full_response)

            try:
                await status_msg.delete()
            except Exception:
                pass

            if not full_response.strip():
                full_response = "✅ Done (no text response)."

            # Notify desktop: response complete
            if bc:
                await bc("response_done", {"text": full_response})

            # Split and send to Telegram
            for chunk in _split_message(full_response):
                await update.message.reply_text(chunk)

        except Exception as e:
            log.error(f"Telegram pipeline error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")
            if bc:
                await bc("error", {"message": f"Telegram pipeline error: {str(e)[:200]}"})


# ── Proactive send functions (called by tools/brain) ──────────
async def send_telegram_message(text: str) -> str:
    """Send a proactive message to the user on Telegram."""
    if not _app or not cfg.TELEGRAM_CHAT_ID:
        return "Telegram not configured or not connected."

    try:
        bot = _app.bot
        for chunk in _split_message(text):
            await bot.send_message(chat_id=cfg.TELEGRAM_CHAT_ID, text=chunk)
        log.info(f"📤 Telegram proactive: \"{text[:60]}\"")
        return "Message sent to Telegram."
    except Exception as e:
        log.error(f"Telegram send error: {e}")
        return f"Failed to send Telegram message: {e}"


async def send_telegram_photo(image_path: str, caption: str = "") -> str:
    """Send a photo to the user on Telegram."""
    if not _app or not cfg.TELEGRAM_CHAT_ID:
        return "Telegram not configured."

    try:
        p = Path(image_path).expanduser()
        if not p.exists():
            return f"Image not found: {image_path}"
        bot = _app.bot
        with open(p, "rb") as f:
            await bot.send_photo(
                chat_id=cfg.TELEGRAM_CHAT_ID,
                photo=f,
                caption=caption[:1024] if caption else None,
            )
        return "Photo sent to Telegram."
    except Exception as e:
        return f"Failed to send photo: {e}"
