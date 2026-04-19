"""
JARVIS — User Preferences

Stores and retrieves user default-app preferences in a JSON file.
These preferences tell JARVIS which apps to use for notes, calendar,
email, music, etc. — so it can act faster without asking.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.preferences")

_PREFS_FILE = Path(__file__).resolve().parent.parent / "user_preferences.json"

# ── Schema: category → {options, default, description} ────────
PREFERENCE_SCHEMA: dict[str, dict[str, Any]] = {
    "notes_app": {
        "label": "Notes App",
        "description": "Where JARVIS saves notes and lists",
        "options": [
            {"value": "apple_notes",    "label": "Apple Notes"},
            {"value": "google_keep",    "label": "Google Keep"},
            {"value": "notion",         "label": "Notion"},
            {"value": "obsidian",       "label": "Obsidian"},
            {"value": "markdown_local", "label": "Local Markdown Files"},
        ],
        "default": "google_keep",
    },
    "calendar_app": {
        "label": "Calendar",
        "description": "Default calendar for events & scheduling",
        "options": [
            {"value": "google_calendar", "label": "Google Calendar"},
            {"value": "apple_calendar",  "label": "Apple Calendar"},
            {"value": "outlook_calendar","label": "Outlook Calendar"},
        ],
        "default": "google_calendar",
    },
    "email_app": {
        "label": "Email",
        "description": "Default email client for checking & sending mail",
        "options": [
            {"value": "gmail",       "label": "Gmail"},
            {"value": "apple_mail",  "label": "Apple Mail"},
            {"value": "outlook",     "label": "Outlook"},
        ],
        "default": "gmail",
    },
    "browser": {
        "label": "Browser",
        "description": "Default web browser for browsing & automation",
        "options": [
            {"value": "brave",   "label": "Brave"},
            {"value": "safari",  "label": "Safari"},
            {"value": "chrome",  "label": "Google Chrome"},
            {"value": "firefox", "label": "Firefox"},
            {"value": "arc",     "label": "Arc"},
        ],
        "default": "brave",
    },
    "music_app": {
        "label": "Music",
        "description": "Default music player for 'play music' commands",
        "options": [
            {"value": "spotify",       "label": "Spotify"},
            {"value": "apple_music",   "label": "Apple Music"},
            {"value": "youtube_music", "label": "YouTube Music"},
        ],
        "default": "spotify",
    },
    "messenger_app": {
        "label": "Messenger",
        "description": "Default messaging app for sending messages",
        "options": [
            {"value": "telegram",  "label": "Telegram"},
            {"value": "whatsapp",  "label": "WhatsApp"},
            {"value": "imessage",  "label": "iMessage"},
        ],
        "default": "telegram",
    },
    "maps_app": {
        "label": "Maps",
        "description": "Default maps app for directions & navigation",
        "options": [
            {"value": "google_maps", "label": "Google Maps"},
            {"value": "apple_maps",  "label": "Apple Maps"},
            {"value": "waze",        "label": "Waze"},
        ],
        "default": "google_maps",
    },
    "search_engine": {
        "label": "Search Engine",
        "description": "Preferred search engine for web lookups",
        "options": [
            {"value": "google",      "label": "Google"},
            {"value": "duckduckgo",  "label": "DuckDuckGo"},
            {"value": "bing",        "label": "Bing"},
        ],
        "default": "google",
    },
    "code_editor": {
        "label": "Code Editor",
        "description": "Default code editor for opening projects",
        "options": [
            {"value": "vscode",  "label": "VS Code"},
            {"value": "cursor",  "label": "Cursor"},
            {"value": "xcode",   "label": "Xcode"},
            {"value": "sublime", "label": "Sublime Text"},
        ],
        "default": "vscode",
    },
    "default_language": {
        "label": "Language",
        "description": "Preferred response language",
        "options": [
            {"value": "english",   "label": "English"},
            {"value": "serbian",   "label": "Serbian"},
            {"value": "slovenian", "label": "Slovenian"},
        ],
        "default": "english",
    },
}


def _load_raw() -> dict[str, str]:
    """Load raw preferences from disk."""
    if _PREFS_FILE.exists():
        try:
            return json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"Failed to read preferences: {e}")
    return {}


def _save_raw(data: dict[str, str]) -> None:
    """Persist preferences to disk."""
    _PREFS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info(f"Preferences saved → {_PREFS_FILE}")


def get_preferences() -> dict[str, str]:
    """Return merged preferences (saved values + defaults for missing keys)."""
    saved = _load_raw()
    merged: dict[str, str] = {}
    for key, schema in PREFERENCE_SCHEMA.items():
        merged[key] = saved.get(key, schema["default"])
    return merged


def set_preferences(updates: dict[str, str]) -> dict[str, str]:
    """Update one or more preferences. Returns the full merged dict."""
    current = get_preferences()
    for key, value in updates.items():
        if key in PREFERENCE_SCHEMA:
            # Validate value is in allowed options
            allowed = [opt["value"] for opt in PREFERENCE_SCHEMA[key]["options"]]
            if value in allowed:
                current[key] = value
            else:
                log.warning(f"Invalid preference value '{value}' for '{key}'. Allowed: {allowed}")
    _save_raw(current)
    return current


def get_schema() -> dict:
    """Return the full schema (for the frontend to build the settings UI)."""
    return PREFERENCE_SCHEMA


# ── Helpers for the AI brain ──────────────────────────────────

# Maps preference values → human-friendly names for the system prompt
_APP_NAMES = {
    # Notes
    "apple_notes": "Apple Notes app (macOS)",
    "google_keep": "Google Keep (https://keep.google.com)",
    "notion": "Notion (https://notion.so)",
    "obsidian": "Obsidian app (macOS)",
    "markdown_local": "local Markdown files in the Notes directory",
    # Calendar
    "google_calendar": "Google Calendar (https://calendar.google.com)",
    "apple_calendar": "Apple Calendar app (macOS)",
    "outlook_calendar": "Outlook Calendar (https://outlook.live.com/calendar)",
    # Email
    "gmail": "Gmail (https://gmail.com)",
    "apple_mail": "Apple Mail app (macOS)",
    "outlook": "Outlook (https://outlook.live.com)",
    # Browser
    "brave": "Brave Browser",
    "safari": "Safari",
    "chrome": "Google Chrome",
    "firefox": "Firefox",
    "arc": "Arc Browser",
    # Music
    "spotify": "Spotify app",
    "apple_music": "Apple Music app",
    "youtube_music": "YouTube Music (https://music.youtube.com)",
    # Messenger
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "imessage": "iMessage / Messages app",
    # Maps
    "google_maps": "Google Maps (https://maps.google.com)",
    "apple_maps": "Apple Maps app",
    "waze": "Waze app",
    # Search
    "google": "Google (https://google.com)",
    "duckduckgo": "DuckDuckGo (https://duckduckgo.com)",
    "bing": "Bing (https://bing.com)",
    # Code editor
    "vscode": "Visual Studio Code",
    "cursor": "Cursor",
    "xcode": "Xcode",
    "sublime": "Sublime Text",
    # Language
    "english": "English",
    "serbian": "Serbian",
    "slovenian": "Slovenian",
}


def get_preferences_for_prompt() -> str:
    """
    Build a system-prompt block that tells the AI the user's default apps.
    This is injected into the Gemini system prompt.
    """
    prefs = get_preferences()
    lines = ["USER'S DEFAULT APP PREFERENCES (always use these unless told otherwise):"]
    for key, value in prefs.items():
        schema = PREFERENCE_SCHEMA.get(key, {})
        label = schema.get("label", key)
        friendly = _APP_NAMES.get(value, value)
        lines.append(f"  • {label}: {friendly}")

    lines.append("")
    lines.append(
        "IMPORTANT: When the user asks to save a note, check calendar, play music, etc. — "
        "use the app listed above by default. Do NOT ask which app to use. "
        "Only ask if the user explicitly mentions a different app."
    )
    return "\n".join(lines)
