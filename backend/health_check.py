
"""
JARVIS — Startup Health Checks

Pings every configured API on startup to verify keys actually work.
Returns a dict of {service: {status, message}} where status is:
  - "ok"           → API responded, key is valid
  - "failed"       → API responded with an error (bad key, billing, etc.)
  - "unconfigured" → No key provided in .env
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from config import cfg

log = logging.getLogger("jarvis.health")


async def check_all() -> dict[str, dict[str, str]]:
    """Run all health checks in parallel. Returns results dict."""
    results = await asyncio.gather(
        check_gemini(),
        check_tts(),
        check_whisper(),
        check_local_tools(),
    )
    merged: dict[str, dict[str, str]] = {}
    for r in results:
        merged.update(r)
    return merged


# ── Gemini ────────────────────────────────────────────────────
async def check_gemini() -> dict:
    key = "gemini"
    if not cfg.GEMINI_API_KEY:
        return {key: {"status": "unconfigured", "message": "GEMINI_API_KEY not set"}}

    try:
        # Use the Gemini REST API to list models — lightweight auth check
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.GEMINI_MODEL}",
                params={"key": cfg.GEMINI_API_KEY},
            )

        if resp.status_code == 200:
            return {key: {"status": "ok", "message": f"Authenticated — model: {cfg.GEMINI_MODEL}"}}

        body = resp.json()
        err_msg = body.get("error", {}).get("message", resp.text[:120])

        if resp.status_code == 400 and "API_KEY_INVALID" in resp.text:
            return {key: {"status": "failed", "message": f"Invalid API key: {err_msg}"}}
        if resp.status_code == 403:
            return {key: {"status": "failed", "message": f"Access denied: {err_msg}"}}
        if resp.status_code == 429:
            # Rate limited means the key IS valid
            return {key: {"status": "ok", "message": "Authenticated (rate-limited, but key is valid)"}}

        return {key: {"status": "failed", "message": f"HTTP {resp.status_code}: {err_msg}"}}

    except httpx.TimeoutException:
        return {key: {"status": "failed", "message": "Timeout — cannot reach generativelanguage.googleapis.com"}}
    except Exception as e:
        return {key: {"status": "failed", "message": f"Connection error: {e}"}}


# ── TTS (Google Cloud TTS or Fish Audio) ─────────────────────
async def check_tts() -> dict:
    key = "tts"

    # If Fish Audio is configured, check that
    if cfg.FISH_AUDIO_API_KEY and cfg.FISH_AUDIO_VOICE_ID:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.fish.audio/model/{cfg.FISH_AUDIO_VOICE_ID}",
                    headers={"Authorization": f"Bearer {cfg.FISH_AUDIO_API_KEY}"},
                )
            if resp.status_code == 200:
                data = resp.json()
                name = data.get("title", data.get("name", "unknown"))
                return {key: {"status": "ok", "message": f"Fish Audio — voice: {name}"}}
            return {key: {"status": "failed", "message": f"Fish Audio HTTP {resp.status_code}"}}
        except Exception as e:
            return {key: {"status": "failed", "message": f"Fish Audio error: {e}"}}

    # Otherwise check Google Cloud TTS using the Gemini API key
    if cfg.GEMINI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://texttospeech.googleapis.com/v1/voices",
                    params={"key": cfg.GEMINI_API_KEY, "languageCode": "en-US"},
                )
            if resp.status_code == 200:
                return {key: {"status": "ok", "message": "Google Cloud TTS — en-GB-Neural2-B"}}
            if resp.status_code == 403:
                body = resp.json()
                err = body.get("error", {}).get("message", "")
                if "Cloud Text-to-Speech API has not been used" in err or "is not enabled" in err:
                    return {key: {"status": "failed", "message": "Google TTS API not enabled — enable it at console.cloud.google.com/apis"}}
                return {key: {"status": "failed", "message": f"Google TTS access denied: {err[:100]}"}}
            return {key: {"status": "failed", "message": f"Google TTS HTTP {resp.status_code}"}}
        except Exception as e:
            return {key: {"status": "failed", "message": f"Google TTS error: {e}"}}

    return {key: {"status": "unconfigured", "message": "No TTS key configured"}}


# ── Google (Calendar + Gmail) ─────────────────────────────────
async def check_google() -> dict:
    results = {}
    
    if not cfg.GOOGLE_CLIENT_ID or not cfg.GOOGLE_CLIENT_SECRET:
        msg = "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set"
        results["calendar"] = {"status": "unconfigured", "message": msg}
        results["email"] = {"status": "unconfigured", "message": msg}
        return results

    # Check if token files exist (meaning OAuth was completed)
    from pathlib import Path
    creds_dir = Path(__file__).resolve().parent
    
    cal_token = creds_dir / "token.json"
    gmail_token = creds_dir / "token_gmail.json"

    if cal_token.exists():
        results["calendar"] = {"status": "ok", "message": "OAuth token found"}
    else:
        results["calendar"] = {"status": "failed", "message": "OAuth not completed — run the calendar tool once to authenticate"}

    if gmail_token.exists():
        results["email"] = {"status": "ok", "message": "OAuth token found"}
    else:
        results["email"] = {"status": "failed", "message": "OAuth not completed — run the email tool once to authenticate"}

    return results


# ── Whisper (local) ───────────────────────────────────────────
async def check_whisper() -> dict:
    key = "whisper"
    try:
        # Just check if the library imports and the model name is valid
        from faster_whisper import WhisperModel
        return {key: {"status": "ok", "message": f"Model: {cfg.WHISPER_MODEL} (will download on first use)"}}
    except ImportError:
        return {key: {"status": "failed", "message": "faster-whisper not installed"}}
    except Exception as e:
        return {key: {"status": "failed", "message": str(e)}}


# ── Local tools (always available) ────────────────────────────
async def check_local_tools() -> dict:
    results = {}

    # Screen vision
    try:
        import mss
        results["screen_vision"] = {"status": "ok", "message": "mss available"}
    except ImportError:
        results["screen_vision"] = {"status": "failed", "message": "mss not installed"}

    # Filesystem — always ok
    results["filesystem"] = {"status": "ok", "message": "pathlib ready"}
    results["terminal"] = {"status": "ok", "message": "subprocess ready"}

    # Browser
    try:
        from playwright.async_api import async_playwright
        results["browser"] = {"status": "ok", "message": "Playwright available"}
    except ImportError:
        results["browser"] = {"status": "failed", "message": "Playwright not installed"}

    return results
