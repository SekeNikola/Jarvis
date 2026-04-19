"""
JARVIS — Configuration
Loads environment variables and exposes typed config.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Walk up to find .env at project root
_root = Path(__file__).resolve().parent.parent
load_dotenv(_root / ".env")


class Config:
    # ── API Keys ──────────────────────────────────────────────
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    FISH_AUDIO_API_KEY: str = os.getenv("FISH_AUDIO_API_KEY", "")
    FISH_AUDIO_VOICE_ID: str = os.getenv("FISH_AUDIO_VOICE_ID", "")

    # ── Telegram ──────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # ── User ──────────────────────────────────────────────────
    USERNAME: str = os.getenv("JARVIS_USERNAME", "User")
    NOTES_DIR: Path = Path(os.getenv("JARVIS_NOTES_DIR", "~/Notes")).expanduser()

    # ── Location ──────────────────────────────────────────────
    LOCATION: str = os.getenv("JARVIS_LOCATION", "Belgrade, Serbia")
    LATITUDE: float = float(os.getenv("JARVIS_LATITUDE", "44.8176"))
    LONGITUDE: float = float(os.getenv("JARVIS_LONGITUDE", "20.4633"))

    # ── Whisper ───────────────────────────────────────────────
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small")

    # ── Gemini ────────────────────────────────────────────────
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_MAX_TOKENS: int = 4096

    # ── Server ────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── Fish Audio TTS ────────────────────────────────────────
    FISH_AUDIO_BASE_URL: str = "https://api.fish.audio/v1/tts"

    # ── Dangerous commands that need confirmation ─────────────
    DANGEROUS_COMMANDS: list[str] = [
        "rm ", "rmdir", "mkfs", "dd ", "format",
        "del ", "shutdown", "reboot", "kill ",
        "sudo rm", "chmod 777", "> /dev/",
    ]

    # ── Screen Watcher Auto-Approve Rules ──────────────────────────
    AUTO_CLICK_RULES = [
        {
            "watch": "Allow button in VS Code",
            "method": "template",          # use saved template
            "template": "vscode-allow",
            "action": "click",
            "confirm": False               # click without asking
        },
        {
            "watch": "OK button any app",
            "method": "text",
            "search_text": "OK",
            "action": "click",
            "confirm": False
        },
        {
            "watch": "Delete confirmation",
            "method": "text", 
            "search_text": "Delete",
            "action": "notify",            # never auto-click, always ask
            "confirm": True
        },
    ]

    # ── Audio ───────────────────────────────────────────────────
    # See available voices by running `say -v '?'` in your terminal
    MACOS_VOICE: str = os.getenv("JARVIS_MACOS_VOICE", "Daniel")

    @classmethod
    def validate(cls) -> list[str]:
        """Return list of missing required keys."""
        missing = []
        if not cls.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        return missing

    @property
    def LOG_LEVEL(self):
        return os.environ.get("LOG_LEVEL", "INFO").upper()

    @property
    def AUTO_CLICK_RULES(self):
        return globals().get("AUTO_CLICK_RULES", [])


cfg = Config()
