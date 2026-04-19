"""
JARVIS — Gemini Brain

The AI core. Wraps the Google Gemini API with:
  - System prompt
  - Tool definitions (function calling)
  - Automatic tool-execution loop
  - Async generator that yields events for the WebSocket layer

Uses the current google-genai SDK (not the deprecated google-generativeai).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from google import genai
from google.genai import types

from config import cfg
from preferences import get_preferences_for_prompt, get_preferences
from user_profile import (
    get_profile_for_prompt,
    learn_fact,
    add_contact,
    add_email_account,
)

log = logging.getLogger("jarvis.brain")


# ── Tool Definitions (Gemini function-calling format) ─────────
TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="take_screenshot",
            description="Capture the current screen. Returns a base64-encoded PNG image. Use this when you need to see what's on the user's screen.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={},
            ),
        ),
        types.FunctionDeclaration(
            name="read_file",
            description="Read the contents of a file at the given path.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Absolute or ~-relative file path.",
                    ),
                },
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="list_directory",
            description="List files and folders in a directory.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Absolute or ~-relative directory path.",
                    ),
                },
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="run_terminal_command",
            description="Execute a shell command and return stdout/stderr. Dangerous commands (rm, sudo, etc.) will be blocked.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "command": types.Schema(
                        type=types.Type.STRING,
                        description="The shell command to run.",
                    ),
                },
                required=["command"],
            ),
        ),
        types.FunctionDeclaration(
            name="smart_browser_execute",
            description=(
                "Launch an Intelligent 3-layer Browser Agent that handles fast HTML parsing, "
                "browser-use automation, and AI Vision fallbacks automatically. "
                "Use this for ANY web task: searching for flights, booking hotels, shopping, "
                "filling out forms, comparing prices, looking up information on specific websites, etc. "
                "Provide the raw natural language voice command to the engine."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "voice_intent": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "The raw natural language voice intent from the user. "
                            "Example: 'find cheap gopro on facebook marketplace under 100 euros'"
                        ),
                    ),
                },
                required=["voice_intent"],
            ),
        ),
        types.FunctionDeclaration(
            name="browser_agent",
            description=(
                "Launch an AI-powered browser agent that controls a REAL visible browser. "
                "The agent can navigate websites, fill forms, click buttons, search, scroll, "
                "extract data — anything a human can do in a browser. Use this for ANY web task: "
                "searching for flights, booking hotels, shopping, filling out forms, comparing prices, "
                "looking up information on specific websites, etc. "
                "Provide a detailed task description including what site to visit and what to do."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "task": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Detailed natural language description of the browser task. "
                            "Be specific: include the website to visit, what fields to fill, "
                            "what buttons to click, what data to extract. "
                            "Example: 'Go to Google Flights, search for flights from Belgrade "
                            "to Ljubljana on June 15, 2025, and show the cheapest options.'"
                        ),
                    ),
                },
                required=["task"],
            ),
        ),
        types.FunctionDeclaration(
            name="create_note",
            description="Create a markdown note and save it to the user's Notes directory.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(
                        type=types.Type.STRING,
                        description="Note title (used as filename).",
                    ),
                    "content": types.Schema(
                        type=types.Type.STRING,
                        description="Markdown content of the note.",
                    ),
                },
                required=["title", "content"],
            ),
        ),
        types.FunctionDeclaration(
            name="send_telegram_message",
            description=(
                "Send a proactive message to the user on Telegram. "
                "Use this when you want to notify the user about something important, "
                "send a reminder, or share information they should know about. "
                "The user will receive this as a Telegram notification on their phone."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "text": types.Schema(
                        type=types.Type.STRING,
                        description="The message text to send.",
                    ),
                },
                required=["text"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_weather",
            description=(
                "Get current weather and 3-day forecast for any location. "
                "Uses free Open-Meteo API — no browser needed. "
                "If no location is specified, returns weather for the user's home location."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "location": types.Schema(
                        type=types.Type.STRING,
                        description="City or place name (e.g. 'Paris', 'New York'). Leave empty for user's home location.",
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="web_search",
            description=(
                "Quick web search that returns top 5 results with titles, snippets, and URLs. "
                "Use this for quick factual lookups, finding addresses, phone numbers, "
                "opening hours, news, etc. — without opening a full browser. "
                "Only use browser_agent when you need to INTERACT with a website (click, fill forms, scroll, compare)."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description="The search query.",
                    ),
                },
                required=["query"],
            ),
        ),
        types.FunctionDeclaration(
            name="set_reminder",
            description=(
                "Set a delayed reminder. After the specified number of seconds, "
                "a Telegram notification will be sent to the user. "
                "Use this when the user says 'remind me in X minutes/hours'. "
                "The tool returns immediately with a confirmation — the actual "
                "notification fires later in the background."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "delay_seconds": types.Schema(
                        type=types.Type.INTEGER,
                        description="Delay in seconds before sending the reminder (e.g. 120 for 2 minutes, 3600 for 1 hour).",
                    ),
                    "message": types.Schema(
                        type=types.Type.STRING,
                        description="The reminder message text the user will receive.",
                    ),
                },
                required=["delay_seconds", "message"],
            ),
        ),
        types.FunctionDeclaration(
            name="control_app",
            description=(
                "Control desktop applications on macOS. Can open, close/quit, focus (bring to front), "
                "minimize, maximize, fullscreen, or hide apps. Can also list all running apps "
                "or get info about the frontmost app. Use this when the user asks to open, close, "
                "switch to, minimize, maximize, or manage desktop applications."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "action": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "The action to perform. One of: "
                            "'open' (launch/activate), 'close'/'quit' (gracefully quit), "
                            "'focus' (bring to front), 'minimize', 'maximize' (fill screen), "
                            "'fullscreen' (toggle native fullscreen), 'hide', "
                            "'list' (list all running apps), 'frontmost' (info about active app)."
                        ),
                    ),
                    "app_name": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "The application name, e.g. 'Safari', 'Finder', 'Spotify', "
                            "'Visual Studio Code', 'Brave Browser'. Not required for 'list' or 'frontmost'."
                        ),
                    ),
                },
                required=["action"],
            ),
        ),
        types.FunctionDeclaration(
            name="type_text",
            description=(
                "Type text into the currently focused application using clipboard paste. "
                "Reliable for long text, special characters, and multi-line content. "
                "Use this to type prompts, messages, code, or any text into desktop apps "
                "like Claude, ChatGPT, Terminal, text editors, etc. "
                "Optionally specify app_name to focus that app first."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "text": types.Schema(
                        type=types.Type.STRING,
                        description="The text to type/paste into the app.",
                    ),
                    "app_name": types.Schema(
                        type=types.Type.STRING,
                        description="Optional: app to focus before typing (e.g. 'Claude', 'Terminal').",
                    ),
                },
                required=["text"],
            ),
        ),
        types.FunctionDeclaration(
            name="press_key",
            description="Press a keyboard key (or key combination).",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "key": types.Schema(
                        type=types.Type.STRING,
                        description="Key to press (e.g. 'return', 'escape', 'a').",
                    ),
                    "modifiers": types.Schema(
                        type=types.Type.STRING,
                        description="Comma-separated modifiers ('command', 'shift').",
                    ),
                    "app_name": types.Schema(
                        type=types.Type.STRING,
                        description="App to focus first.",
                    ),
                },
                required=["key"],
            ),
        ),
        types.FunctionDeclaration(
            name="smart_click",
            description="Find and click any visible UI element on the screen (buttons, links, icons, etc.) by describing it. It works inside any application.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "description": types.Schema(
                        type=types.Type.STRING,
                        description="Description of the button/element to click.",
                    ),
                    "confirm": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Require user confirmation before clicking.",
                    ),
                },
                required=["description"],
            ),
        ),
        types.FunctionDeclaration(
            name="human_scroll",
            description="Scroll the screen in a human-like manner.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "amount": types.Schema(
                        type=types.Type.INTEGER,
                        description="Amount to scroll (number of steps).",
                    ),
                    "direction": types.Schema(
                        type=types.Type.STRING,
                        description="'up' or 'down'",
                    ),
                },
                required=["amount", "direction"],
            ),
        ),
        types.FunctionDeclaration(
            name="human_right_click",
            description="Right click at current mouse position or given coordinates.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "x": types.Schema(
                        type=types.Type.INTEGER,
                        description="X coordinate (optional, defaults to current mouse position).",
                    ),
                    "y": types.Schema(
                        type=types.Type.INTEGER,
                        description="Y coordinate (optional, defaults to current mouse position).",
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="watch_for",
            description="Watch the screen for a specific element in the background.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "description": types.Schema(
                        type=types.Type.STRING,
                        description="Element to watch for.",
                    ),
                    "auto_click": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Whether to auto-click when found.",
                    ),
                },
                required=["description"],
            ),
        ),
        types.FunctionDeclaration(
            name="stop_watching",
            description="Stop background screen watchers.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "description": types.Schema(
                        type=types.Type.STRING,
                        description="Specific watcher to stop, or empty to stop all.",
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="save_template",
            description="Save a screen region as a template for fast matching later.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING),
                    "x": types.Schema(type=types.Type.INTEGER),
                    "y": types.Schema(type=types.Type.INTEGER),
                    "w": types.Schema(type=types.Type.INTEGER),
                    "h": types.Schema(type=types.Type.INTEGER),
                },
                required=["name", "x", "y", "w", "h"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_active_window_title",
            description="Get the title of the currently focused window.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={},
            ),
        ),
        types.FunctionDeclaration(
            name="wait_seconds",
            description="Wait for a specific duration.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "seconds": types.Schema(
                        type=types.Type.NUMBER,
                        description="Number of seconds to wait (1-30).",
                    ),
                },
                required=["seconds"],
            ),
        ),
        types.FunctionDeclaration(
            name="learn_user_fact",
            description=(
                "Remember a personal fact about the user for future reference. "
                "Call this AUTOMATICALLY whenever the user mentions personal info you should remember: "
                "allergies, preferences, habits, birthday, family info, favorite things, etc. "
                "Do NOT announce you're saving it — just quietly store it and continue the conversation. "
                "Only save genuinely useful long-term facts, not trivial chat details."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "fact": types.Schema(
                        type=types.Type.STRING,
                        description="The fact to remember, e.g. 'User is vegetarian', 'User's birthday is March 15'.",
                    ),
                },
                required=["fact"],
            ),
        ),
        types.FunctionDeclaration(
            name="add_user_email_account",
            description=(
                "Save or update an email account in the user's profile. "
                "Call this when the user mentions an email address you should remember. "
                "If they say 'use this as default' or 'this is my main email', set default=true."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "address": types.Schema(
                        type=types.Type.STRING,
                        description="The email address, e.g. 'user@gmail.com'.",
                    ),
                    "label": types.Schema(
                        type=types.Type.STRING,
                        description="Optional label: 'personal', 'work', 'school', etc.",
                    ),
                    "default": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Whether this should be the default email account.",
                    ),
                },
                required=["address"],
            ),
        ),
        types.FunctionDeclaration(
            name="add_user_contact",
            description=(
                "Save or update a person in the user's contacts. "
                "Call this when the user mentions someone they interact with frequently "
                "and provides contact details like phone, email, or relation."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(
                        type=types.Type.STRING,
                        description="Person's name.",
                    ),
                    "relation": types.Schema(
                        type=types.Type.STRING,
                        description="Relation to user: 'mother', 'friend', 'coworker', 'boss', etc.",
                    ),
                    "phone": types.Schema(
                        type=types.Type.STRING,
                        description="Phone number.",
                    ),
                    "email": types.Schema(
                        type=types.Type.STRING,
                        description="Email address.",
                    ),
                    "notes": types.Schema(
                        type=types.Type.STRING,
                        description="Any extra notes, e.g. 'prefers WhatsApp', 'works at Google'.",
                    ),
                },
                required=["name"],
            ),
        ),
    ]
)


# ── System Prompt ─────────────────────────────────────────────
def _build_system_prompt() -> str:
    prefs = get_preferences()
    prefs_block = get_preferences_for_prompt()
    profile_block = get_profile_for_prompt()

    # Build notes-app-specific instructions based on user preference
    notes_pref = prefs.get("notes_app", "google_keep")
    if notes_pref == "google_keep":
        notes_instructions = (
            f"NOTES — GOOGLE KEEP (user's default):\n"
            f"When the user asks to save a note, add to a list, or jot something down:\n"
            f"  - ALWAYS assume the list ALREADY EXISTS unless the user explicitly says 'create a new'.\n"
            f"  - Use browser_agent to open https://keep.google.com, find the note, add items.\n"
            f"  - Do NOT create a new note unless explicitly asked.\n"
            f"  - Always wait for notes to load, find the existing note, and click Close when done.\n"
        )
    elif notes_pref == "apple_notes":
        notes_instructions = (
            f"NOTES — APPLE NOTES (user's default):\n"
            f"When the user asks to save a note or jot something down:\n"
            f"  - Use control_app to open Apple Notes\n"
            f"  - Use press_key(key='n', modifiers='command') to create a new note\n"
            f"  - Use type_text to type the note content\n"
            f"  - Notes save automatically in Apple Notes.\n"
        )
    elif notes_pref == "notion":
        notes_instructions = (
            f"NOTES — NOTION (user's default):\n"
            f"When the user asks to save a note:\n"
            f"  - Use browser_agent to open https://notion.so\n"
            f"  - Navigate to the appropriate page and add the content.\n"
        )
    elif notes_pref == "obsidian":
        notes_instructions = (
            f"NOTES — OBSIDIAN (user's default):\n"
            f"When the user asks to save a note:\n"
            f"  - Use control_app to open Obsidian\n"
            f"  - Use press_key(key='n', modifiers='command') to create a new note\n"
            f"  - Use type_text to write the note content (Markdown supported).\n"
        )
    else:  # markdown_local
        notes_instructions = (
            f"NOTES — LOCAL MARKDOWN FILES (user's default):\n"
            f"When the user asks to save a note:\n"
            f"  - Use the create_note tool to save a .md file in the Notes directory.\n"
        )

    # Language preference
    lang_pref = prefs.get("default_language", "english")
    lang_map = {"english": "English", "serbian": "Serbian", "slovenian": "Slovenian"}
    default_lang = lang_map.get(lang_pref, "English")

    return (
        f"You are JARVIS, a personal AI assistant. You are direct, precise, and efficient.\n"
        f"Keep responses concise — you are speaking aloud, not writing an essay.\n"
        f"Never explain what you're about to do. Just do it.\n\n"
        f"CURRENT USER: {cfg.USERNAME}\n"
        f"LOCATION: {cfg.LOCATION} (lat {cfg.LATITUDE}, lon {cfg.LONGITUDE})\n"
        f"Use this location as default for weather, nearby places, directions, etc.\n\n"
        f"{prefs_block}\n\n"
        f"{profile_block}\n\n"
        f"LANGUAGE:\n"
        f"You understand English, Serbian (srpski), and Slovenian (slovenščina).\n"
        f"DEFAULT to {default_lang} unless the user's message is clearly in another supported language.\n"
        f"If the user writes/speaks in Serbian, respond in Serbian. Same for Slovenian.\n"
        f"If you are unsure about the language, always use {default_lang}.\n"
        f"When using browser_agent, write the task description in English for the browser AI,\n"
        f"but translate place names and search terms from the user's language as needed.\n\n"
        f"SMART TOOL ROUTING — THINK BEFORE USING THE BROWSER:\n"
        f"You have several tools. Pick the LIGHTEST one that gets the job done:\n\n"
        f"  1. YOUR OWN KNOWLEDGE (no tool needed):\n"
        f"     - General facts, math, conversions, definitions, translations\n"
        f"     - Advice, explanations, coding help, recipes\n"
        f"     - Time zones, country info, historical facts\n"
        f"     → Just answer directly. No tool call needed.\n\n"
        f"  2. get_weather (instant, no browser):\n"
        f"     - 'What's the weather?' → get_weather() with no args (uses your home location)\n"
        f"     - 'Weather in Paris' → get_weather(location='Paris')\n"
        f"     - Any weather/temperature/forecast question\n"
        f"     → NEVER open a browser for weather. Always use get_weather.\n\n"
        f"  3. web_search (fast, no browser):\n"
        f"     - Quick facts: 'What time does IKEA close?', 'Phone number for ...'\n"
        f"     - News: 'Latest news about ...', 'Did X happen?'\n"
        f"     - Addresses, opening hours, store locations\n"
        f"     - Quick lookups that just need a search result\n"
        f"     → Returns top 5 results with snippets. Fast and lightweight.\n\n"
        f"  4. browser_agent (heavy, use only when needed):\n"
        f"     - INTERACTIVE tasks: filling forms, clicking buttons, logging in\n"
        f"     - VISUAL tasks: comparing products on a page, reading complex layouts\n"
        f"     - MULTI-STEP tasks: booking flights, shopping, ordering food\n"
        f"     - Checking email (Gmail), calendar (Google Calendar)\n"
        f"     - Any task that requires navigating through a website\n"
        f"     → This opens a real browser on screen. Only use when simpler tools won't work.\n\n"
        f"  5. control_app: instant, controls desktop apps\n"
        f"     - 'Open Spotify' → control_app(action='open', app_name='Spotify')\n"
        f"     - 'Close Safari' → control_app(action='close', app_name='Safari')\n"
        f"     - 'Switch to Finder' → control_app(action='focus', app_name='Finder')\n"
        f"     - 'Minimize this' → control_app(action='minimize', app_name=frontmost app)\n"
        f"     - 'What apps are running?' → control_app(action='list')\n"
        f"     - 'What app is this?' → control_app(action='frontmost')\n"
        f"     → Use for opening, closing, switching, minimizing, maximizing, fullscreening apps.\n"
        f"     → If user says 'open X' and X is a DESKTOP APP (Spotify, Discord, Photos, Mail, etc.), use this.\n"
        f"     → If user says 'open X' and X is a WEBSITE (Facebook, Gmail, Twitter, YouTube, etc.), use browser_agent.\n\n"
        f"EXAMPLES of what NOT to use browser for:\n"
        f"  - 'What's the weather?' → get_weather (NOT browser)\n"
        f"  - 'What's the capital of France?' → Just answer (NOT browser)\n"
        f"  - 'Convert 100 USD to EUR' → Just answer (NOT browser)\n"
        f"  - 'What time is it in Tokyo?' → Just answer (NOT browser)\n"
        f"  - 'Find me a pizza place nearby' → web_search (NOT browser)\n"
        f"  - 'News about Tesla' → web_search (NOT browser)\n\n"
        f"EXAMPLES of when TO use browser:\n"
        f"  - 'Book me a flight to Ljubljana' → browser_agent\n"
        f"  - 'Check my email' → browser_agent (Gmail)\n"
        f"  - 'Order food from Wolt' → browser_agent\n"
        f"  - 'Compare prices for iPhone 16 on multiple sites' → browser_agent\n"
        f"  - 'Fill out this form for me' → browser_agent\n\n"
        f"EMAIL & CALENDAR:\n"
        f"For email, use the user's default: {prefs.get('email_app', 'gmail')}.\n"
        f"For calendar, use the user's default: {prefs.get('calendar_app', 'google_calendar')}.\n"
        f"  - If the default is a web service (Gmail, Google Calendar, Outlook web), use browser_agent.\n"
        f"  - If the default is a native app (Apple Mail, Apple Calendar), use control_app to open it.\n"
        f"  - The browser has the user's logged-in Brave profile with cookies.\n"
        f"  - Use the email account from the USER PROFILE section above (if available).\n\n"
        f"{notes_instructions}\n"
        f"BROWSER AUTOMATION DETAILS:\n"
        f"When using browser_agent, provide a DETAILED and PRECISE task description:\n"
        f"  - Which website URL to go to (always use full URLs like https://keep.google.com)\n"
        f"  - What specific actions to take, step by step\n"
        f"  - What data to extract or what outcome is expected\n"
        f"  - IMPORTANT: Tell the agent to do ONE thing, not multiple. Be surgical.\n"
        f"  - IMPORTANT: Tell the agent when to STOP. Say 'then close/save' or 'then stop'.\n"
        f"  - IMPORTANT: Never give vague instructions like 'add bread to Keep'.\n"
        f"    Instead give exact steps: 'Go to keep.google.com, find the Shopping list note,\n"
        f"    click on it, click + List item, type bread, press Enter, close the note.'\n"
        f"The browser opens visibly on the user's screen.\n\n"
        f"THOROUGH SEARCH BEHAVIOR:\n"
        f"When finding best deals or comparing products (via browser_agent):\n"
        f"  - Check MULTIPLE sources (2-3 websites minimum)\n"
        f"  - Sort by price, compare options, scroll through results\n"
        f"  - Report TOP 3-5 options with price, source, and key details\n"
        f"  - Note suspiciously cheap deals (potential scam)\n\n"
        f"TELEGRAM & REMINDERS:\n"
        f"You can message the user on Telegram using send_telegram_message (instant).\n"
        f"For DELAYED reminders ('remind me in 5 minutes'), use the set_reminder tool.\n"
        f"  - Convert the user's time to seconds: '2 minutes' → 120, '1 hour' → 3600, '30 min' → 1800\n"
        f"  - set_reminder will schedule a background Telegram notification after the delay.\n"
        f"  - NEVER use send_telegram_message for reminders — that sends IMMEDIATELY.\n"
        f"  - Confirm to the user: 'I'll remind you in X minutes.'\n\n"
        f"DESKTOP APP AUTOMATION — TYPE & INTERACT WITH APPS:\n"
        f"You can control desktop apps and type into them. Key tools:\n"
        f"  - control_app: open, close, focus, minimize, maximize apps\n"
        f"  - type_text: type/paste text into any focused app (uses clipboard for reliability)\n"
        f"  - press_key: press keys like Enter, Tab, Escape, or shortcuts like Cmd+Enter\n"
        f"  - take_screenshot: see what's on screen to check results\n"
        f"  - smart_click: find and click ANY element on screen by describing it (e.g. 'Allow button', 'the blue button').\n"
        f"  - human_scroll: natural scrolling momentum.\n"
        f"  - human_right_click: open context menus.\n"
        f"  - watch_for: background agent that waits for a button/window to appear and clicks it automatically.\n"
        f"  - save_template: learn a new UI element by capturing its region.\n"
        f"  - get_active_window_title: find out exactly what screen the user is looking at.\n\n"
        f"WORKFLOW — 'Open X and write/do Y':\n"
        f"When the user says 'open [app] and write [something]', follow this EXACT pattern:\n"
        f"  1. control_app(action='open', app_name='AppName') — open/focus the app\n"
        f"  2. NAVIGATE to the right input field FIRST using keyboard shortcuts (see below)\n"
        f"  3. type_text(text='the text...') — paste the text into the focused field\n"
        f"  4. press_key to submit (Enter, Cmd+Enter, etc. depending on app)\n"
        f"  5. take_screenshot() — verify it worked\n"
        f"  6. If iterating, read the response from screenshot, type follow-up, submit, screenshot again\n"
        f"  7. Report back to the user when done\n\n"
        f"APP-SPECIFIC KEYBOARD SHORTCUTS (CRITICAL — memorize these):\n"
        f"  Visual Studio Code / VS Code / Code:\n"
        f"    - Open Copilot Chat panel: press_key(key='i', modifiers='control,command')\n"
        f"    - Open inline chat: press_key(key='i', modifiers='command')\n"
        f"    - New file: press_key(key='n', modifiers='command')\n"
        f"    - Open terminal: press_key(key='`', modifiers='control')\n"
        f"    - Command palette: press_key(key='p', modifiers='command,shift')\n"
        f"    - Submit in Copilot Chat: press_key(key='return')\n"
        f"    WORKFLOW for VS Code AI chat:\n"
        f"      1. If the user says 'write here in the chat', ASSUME it's already open and focused! DO NOT press the open shortcut.\n"
        f"      2. Otherwise: control_app(action='open', app_name='Visual Studio Code') then press_key(key='i', modifiers='control,command') to open it.\n"
        f"      3. type_text(text='your prompt here')\n"
        f"      4. press_key(key='return') — submit\n\n"
        f"COMPLEX WORKFLOW EXAMPLE — Create a project in VS Code:\n"
        f"User: 'create a new folder on the root called test and open it in vs code and using vs code ai chat create website about video games review.'\n"
        f"Your thought process and tool calls:\n"
        f"  1.  **Create folder**: `run_terminal_command(command='mkdir /Users/adela/test')`\n"
        f"  2.  **Open in VS Code**: `run_terminal_command(command='code /Users/adela/test')`. This is better than `control_app` because it opens the specific folder.\n"
        f"  3.  **Wait for app to open**: `wait_seconds(seconds=5)` to ensure VS Code has loaded the folder.\n"
        f"  4.  **Open AI Chat**: `press_key(key='i', modifiers='control,command', app_name='Visual Studio Code')` to open the Copilot chat panel.\n"
        f"  5.  **Type the prompt**: `type_text(text='Create a simple but stylish website about video game reviews. Include sections for latest reviews, top rated games, and about page. Use HTML, CSS, and basic JavaScript.', app_name='Visual Studio Code')`.\n"
        f"  6.  **Submit to AI**: `press_key(key='return', app_name='Visual Studio Code')`.\n"
        f"  7.  **Monitor Progress**: `wait_seconds(seconds=15)` for the AI to generate the files. Then `take_screenshot()` to see the result. The AI might ask to create files. I should look for 'Create Workspace' or similar buttons and use `smart_click`.\n"
        f"  8.  **Approve file creation**: If the AI chat shows a 'Create Workspace' or 'Accept' button, `smart_click(description='Create Workspace button')`.\n"
        f"  9.  **Final Verification**: `wait_seconds(seconds=10)`. Then `list_directory(path='/Users/adela/test')` to confirm files were created. Then `take_screenshot()` to show the final state.\n"
        f"  10. **Report to user**: 'I have created the folder, opened it in VS Code, and instructed the AI chat to build the website. The files are now available in the /Users/adela/test directory. Here is a screenshot of the result.'\n\n"
        f"  Claude desktop app:\n"
        f"    - New conversation: press_key(key='n', modifiers='command')\n"
        f"    - Submit prompt: press_key(key='return', modifiers='command')\n\n"
        f"  ChatGPT desktop app:\n"
        f"    - Submit prompt: press_key(key='return')\n\n"
        f"  Terminal / iTerm:\n"
        f"    - Just type_text then press_key(key='return')\n\n"
        f"  Notes / TextEdit / any text editor:\n"
        f"    - Just type_text directly, no special shortcut needed\n\n"
        f"CRITICAL RULES for app automation:\n"
        f"  - ALWAYS open the correct input field/panel BEFORE typing (e.g. Copilot Chat in VS Code)\n"
        f"  - NEVER type_text immediately after opening an app — first navigate to the right field\n"
        f"  - NEVER use browser_agent to fix system permissions or open System Settings\n"
        f"  - If you get an accessibility permission error, just TELL the user to fix it manually\n"
        f"  - Use smart_click('button description') to click anything, it uses fast OpenCV and falls back to Gemini Vision.\n"
        f"  - If you need to wait for a long process, use watch_for('success message') to notify the user later.\n"
        f"  - Always take_screenshot after submitting to see the result before iterating\n"
        f"  - When iterating, wait a few seconds for the AI to respond before taking a screenshot\n"
        f"  - If the response is still generating (loading indicator), wait and screenshot again\n"
        f"  - When done, report a summary of what was accomplished to the user\n\n"
        f"SCREEN & VISION:\n"
        f"You can SEE the user's screen. NEVER say you can't see it.\n"
        f"When asked 'what's on my screen' or similar, use take_screenshot and describe the image in detail.\n"
        f"There is a 5-second cooldown between screenshots to prevent spamming.\n\n"
        f"OPENING APPS — IMPORTANT:\n"
        f"When the user asks to 'open [app]' or 'open [website/app]':\n"
        f"  - For DESKTOP APPS (Spotify, Discord, Photos, Mail, etc.):\n"
        f"    Use control_app(action='open', app_name='AppName')\n"
        f"    The app's built-in wait will ensure it's loaded before responding.\n"
        f"  - For WEBSITES (Facebook, Gmail, Twitter, etc.):\n"
        f"    Use browser_agent with task='Open [website URL] in the browser'\n"
        f"  - ALWAYS take a screenshot after opening to confirm the app/website is visible\n"
        f"  - If the user just asks to 'open X' without follow-up, still take a screenshot to verify\n"
    )

# ── Cooldown for Screenshot Tool ──────────────────────────────
_last_screenshot_time = 0

# ── Tool Executor ─────────────────────────────────────────────
# Optional callback for browser step progress — set by GeminiBrain.chat()
_browser_step_callback = None


async def _execute_tool(name: str, input_data: dict) -> str | dict:
    """
    Dispatch a tool call to the appropriate handler.
    Returns a string result, or a dict with {"text": ..., "screenshot_b64": ...} for screenshots.
    """
    global _last_screenshot_time
    try:
        if name == "take_screenshot":
            import time
            current_time = time.time()
            if current_time - _last_screenshot_time < 5:
                return "You've taken a screenshot very recently. Please wait a few seconds before trying again."
            _last_screenshot_time = current_time

            from tools.vision import take_screenshot
            result = await take_screenshot()
            if isinstance(result, list) and result:
                # Extract the base64 image data
                b64_data = result[0].get("source", {}).get("data", "")
                if b64_data:
                    return {
                        "text": "Screenshot captured. The image is attached — analyze it to see what's on screen.",
                        "screenshot_b64": b64_data,
                    }
            return "Failed to capture screenshot."

        elif name == "read_file":
            from tools.filesystem import read_file
            return await read_file(input_data["path"])

        elif name == "list_directory":
            from tools.filesystem import list_directory
            return await list_directory(input_data["path"])

        elif name == "run_terminal_command":
            from tools.terminal import run_terminal_command
            return await run_terminal_command(input_data["command"])

        elif name == "smart_browser_execute":
            from tools.smart_browser import SmartBrowser, format_results
            sb = SmartBrowser()
            result = await sb.execute(input_data["voice_intent"])
            if result.success:
                formatted = await format_results(result.data, await sb.parse_intent(input_data["voice_intent"]))
                return f"Browser Task Succeeded (method: {result.method}): {formatted}"
            else:
                return f"Browser Task Failed: {result.error}"

        elif name == "browser_agent":
            from tools.browser import run_browser_agent
            return await run_browser_agent(
                input_data["task"],
                on_step=_browser_step_callback,
            )

        elif name == "create_note":
            from tools.filesystem import create_note
            return await create_note(input_data["title"], input_data["content"])

        elif name == "send_telegram_message":
            from clients.telegram_client import send_telegram_message
            return await send_telegram_message(input_data["text"])

        elif name == "get_weather":
            from tools.web_search import get_weather
            return await get_weather(
                location=input_data.get("location"),
            )

        elif name == "web_search":
            from tools.web_search import web_search
            return await web_search(input_data["query"])

        elif name == "set_reminder":
            from tools.scheduler import set_reminder
            return await set_reminder(
                delay_seconds=int(input_data["delay_seconds"]),
                message=input_data["message"],
            )

        elif name == "control_app":
            from tools.app_control import control_app
            return await control_app(
                action=input_data["action"],
                app_name=input_data.get("app_name"),
            )

        elif name == "type_text":
            from tools.app_control import type_text
            return await type_text(
                text=input_data["text"],
                app_name=input_data.get("app_name"),
            )

        elif name == "press_key":
            from tools.app_control import press_key
            return await press_key(
                key=input_data["key"],
                modifiers=input_data.get("modifiers"),
                app_name=input_data.get("app_name"),
            )

        elif name == "smart_click":
            from tools.screen_watcher import smart_click
            success = await smart_click(
                description=input_data["description"],
                confirm=input_data.get("confirm", False)
            )
            return "✅ Clicked element" if success else f"❌ Could not find/click '{input_data['description']}'"

        elif name == "human_scroll":
            from tools.human_mouse import human_scroll
            import pyautogui
            x, y = pyautogui.position()
            human_scroll(x, y, input_data["amount"], input_data["direction"])
            return f"✅ Scrolled {input_data['direction']} {input_data['amount']} steps"

        elif name == "human_right_click":
            from tools.human_mouse import human_right_click
            import pyautogui
            x = input_data.get("x")
            y = input_data.get("y")
            if x is None or y is None:
                x, y = pyautogui.position()
            human_right_click(x, y)
            return f"✅ Right clicked at ({x}, {y})"

        elif name == "watch_for":
            from tools.screen_watcher import watch_for
            watch_for(
                description=input_data["description"],
                auto_click=input_data.get("auto_click", False)
            )
            return f"✅ Watching for '{input_data['description']}' in background"

        elif name == "stop_watching":
            from tools.screen_watcher import stop_watching
            stop_watching(input_data.get("description"))
            return "✅ Stopped watching"

        elif name == "save_template":
            from tools.screen_watcher import save_template
            return save_template(
                name=input_data["name"],
                x=input_data["x"],
                y=input_data["y"],
                w=input_data["w"],
                h=input_data["h"]
            )

        elif name == "get_active_window_title":
            from tools.app_control import get_active_window_title
            title = await get_active_window_title()
            return f"Active window title: '{title}'" if title else "No active window found"

        elif name == "wait_seconds":
            seconds = min(max(float(input_data.get("seconds", 1)), 0.5), 30)
            await asyncio.sleep(seconds)
            return f"✅ Waited {seconds} seconds"

        elif name == "learn_user_fact":
            learn_fact(input_data["fact"])
            return "✅ Fact saved to user profile."

        elif name == "add_user_email_account":
            add_email_account(
                address=input_data["address"],
                default=input_data.get("default", False),
                label=input_data.get("label", ""),
            )
            return f"✅ Email account {input_data['address']} saved to profile."

        elif name == "add_user_contact":
            add_contact(
                name=input_data["name"],
                relation=input_data.get("relation", ""),
                phone=input_data.get("phone", ""),
                email=input_data.get("email", ""),
                notes=input_data.get("notes", ""),
            )
            return f"✅ Contact '{input_data['name']}' saved to profile."

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        log.error(f"Tool '{name}' failed: {e}")
        return f"Tool error: {e}"


# ── Gemini Brain ──────────────────────────────────────────────
class GeminiBrain:
    """
    Async interface to Gemini with automatic tool-call loop.

    Usage:
        brain = GeminiBrain()
        async for event in brain.chat(messages):
            # event is {"type": "...", ...}
    """

    def __init__(self):
        self.client = genai.Client(api_key=cfg.GEMINI_API_KEY)
        self.model = cfg.GEMINI_MODEL
        self.system_prompt = _build_system_prompt()

    def _build_system_prompt(self):
        """Rebuild system prompt (e.g. after preference changes)."""
        return _build_system_prompt()

    async def chat(self, messages: list[dict], on_browser_step=None) -> AsyncGenerator[dict, None]:
        """
        Send messages to Gemini and yield events.

        Automatically handles the tool-use loop:
          1. Send messages → Gemini responds
          2. If Gemini wants to call tools → execute them
          3. Append tool results → send again
          4. Repeat until Gemini gives a final text response

        Args:
            messages: Conversation history
            on_browser_step: Optional async callback for browser agent progress

        Yields:
            {"type": "tool_call",    "tool": str, "input": dict}
            {"type": "tool_result",  "tool": str, "result": Any}
            {"type": "text_delta",   "text": str}
            {"type": "text_done",    "text": str}
        """
        global _browser_step_callback
        _browser_step_callback = on_browser_step
        # Convert our message format to Gemini Content format
        contents = _convert_messages(messages)

        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=[TOOL_DECLARATIONS],
            max_output_tokens=cfg.GEMINI_MAX_TOKENS,
            temperature=0.7,
        )

        max_iterations = 15  # safety limit (browser tasks may need more)

        for _ in range(max_iterations):
            # Call Gemini
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0]
            log.info(f"Gemini parts={len(candidate.content.parts)}, "
                     f"finish_reason={candidate.finish_reason}")

            # Process response parts
            text_parts: list[str] = []
            function_calls: list[dict] = []

            for part in candidate.content.parts:
                if part.text:
                    text_parts.append(part.text)
                    yield {"type": "text_delta", "text": part.text}

                if part.function_call:
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}
                    function_calls.append({
                        "name": fc.name,
                        "args": args,
                    })

            full_text = "".join(text_parts)

            # If no function calls, we're done
            if not function_calls:
                yield {"type": "text_done", "text": full_text}
                return

            # ── Tool execution loop ──────────────────────────
            # Add assistant's response to contents
            contents.append(candidate.content)

            # Execute tools and build function responses
            function_response_parts = []
            for fc in function_calls:
                yield {
                    "type": "tool_call",
                    "tool": fc["name"],
                    "input": fc["args"],
                }

                result = await _execute_tool(fc["name"], fc["args"])

                # Handle screenshot results (contains image data)
                screenshot_b64 = None
                if isinstance(result, dict) and "screenshot_b64" in result:
                    screenshot_b64 = result["screenshot_b64"]
                    result_str = result["text"]
                else:
                    result_str = result if isinstance(result, str) else json.dumps(result, default=str)

                yield {
                    "type": "tool_result",
                    "tool": fc["name"],
                    "result": result_str,
                    "screenshot_b64": screenshot_b64,
                }

                # Add function response part
                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fc["name"],
                        response={"result": result_str},
                    )
                )

                # If this was a screenshot, also add the image so Gemini can SEE it
                if screenshot_b64:
                    import base64 as b64_mod
                    img_bytes = b64_mod.b64decode(screenshot_b64)
                    function_response_parts.append(
                        types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                    )

            # Add tool results as user turn and loop
            contents.append(
                types.Content(role="user", parts=function_response_parts)
            )

        # Max iterations reached
        yield {
            "type": "text_done",
            "text": full_text if text_parts else "I ran into a loop processing tools. Here's what I found so far.",
        }


def _convert_messages(messages: list[dict]) -> list[types.Content]:
    """Convert our internal message format to Gemini Content objects."""
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=content)],
                )
            )
    return contents
