"""JARVIS — Browser Automation Tool (powered by browser-use)

Uses the browser-use library to control a REAL visible browser (Brave).
JARVIS can navigate websites, fill forms, click buttons, search,
book flights, shop — anything a human can do in a browser.

The LLM (Gemini) drives the browser autonomously:
  screenshot → decide action → execute → repeat until done.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import ssl
import certifi
from pathlib import Path
from typing import Any, Callable, Awaitable

# Fix SSL certs before browser-use tries to download extensions
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

from browser_use import Agent, Browser
from browser_use.llm.google import ChatGoogle

from config import cfg

log = logging.getLogger("jarvis.tools.browser")

# ── Brave browser path (macOS) ────────────────────────────────
_BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
_BRAVE_USER_DATA = os.path.expanduser(
    "~/Library/Application Support/BraveSoftware/Brave-Browser"
)
_BRAVE_PROFILE = "Default"

# JARVIS keeps its own copy of the profile to avoid locking conflicts
_JARVIS_PROFILE_DIR = os.path.expanduser("~/.jarvis/browser-profile")

# ── Persistent browser session ────────────────────────────────
_browser: Browser | None = None


def _ensure_jarvis_profile() -> str | None:
    """Copy Brave's cookies & login state into JARVIS's own profile dir.

    Only copies the essential credential files so the profile stays
    lightweight. Skips the copy if it was already done (checks marker).
    Returns the path to the JARVIS user-data dir, or None on failure.
    """
    src = Path(_BRAVE_USER_DATA, _BRAVE_PROFILE)
    if not src.is_dir():
        log.warning("⚠️  Brave profile not found — will use a fresh profile")
        return None

    dst = Path(_JARVIS_PROFILE_DIR, _BRAVE_PROFILE)
    marker = dst / ".jarvis_synced"

    # Re-sync if marker is missing (first run or manual delete)
    if not marker.exists():
        log.info("📦 Syncing Brave credentials into JARVIS profile...")
        dst.mkdir(parents=True, exist_ok=True)

        # Essential files for logged-in sessions
        _FILES_TO_COPY = [
            "Cookies", "Cookies-journal",
            "Login Data", "Login Data-journal",
            "Web Data", "Web Data-journal",
            "Local State",
            "Preferences", "Secure Preferences",
            "Extension Cookies", "Extension Cookies-journal",
        ]
        for fname in _FILES_TO_COPY:
            s = src / fname
            if s.exists():
                shutil.copy2(s, dst / fname)
                log.debug(f"  copied {fname}")

        # Also copy Local State from the parent (user-data) dir
        ls = Path(_BRAVE_USER_DATA, "Local State")
        ls_dst = Path(_JARVIS_PROFILE_DIR, "Local State")
        if ls.exists():
            shutil.copy2(ls, ls_dst)

        marker.touch()
        log.info("✅ Brave credentials synced into JARVIS profile")

        # Disable session restore so Brave doesn't reopen old tabs
        prefs_file = dst / "Preferences"
        if prefs_file.exists():
            try:
                prefs = json.loads(prefs_file.read_text())
                prefs.setdefault("session", {})["restore_on_startup"] = 4  # 4 = open blank/URLs list
                prefs.get("session", {}).pop("startup_urls", None)
                prefs.setdefault("profile", {})["exit_type"] = "Normal"
                prefs_file.write_text(json.dumps(prefs))
                log.info("🔧 Disabled session restore in copied Preferences")
            except Exception as e:
                log.warning(f"Could not patch Preferences: {e}")
    else:
        log.info("👤 Using cached JARVIS browser profile")

    return _JARVIS_PROFILE_DIR


async def _get_browser() -> Browser:
    """Get or create a persistent headed Brave browser session.

    Uses a JARVIS-private copy of the Brave profile so all cookies &
    logged-in sessions (Amazon, Google, etc.) are available without
    locking conflicts with the real Brave browser.
    """
    global _browser
    if _browser is None:
        brave_exists = Path(_BRAVE_PATH).exists()

        extra: dict[str, Any] = {}
        if brave_exists:
            extra["executable_path"] = _BRAVE_PATH
            log.info("🦁 Using Brave Browser")
        else:
            log.info("⚠️  Brave not found, using bundled Chromium")

        # Use JARVIS's own copy of the Brave profile
        jarvis_profile = _ensure_jarvis_profile()
        if jarvis_profile:
            extra["user_data_dir"] = jarvis_profile
            extra["profile_directory"] = _BRAVE_PROFILE
            log.info(f"👤 Profile dir: {jarvis_profile}")

        _browser = Browser(
            headless=False,
            disable_security=True,
            keep_alive=False,  # Set to False so it doesn't zombie-restart when manually closed
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-session-crashed-bubble",
                "--hide-crash-restore-bubble",
            ],
            **extra,
        )
        log.info("🌐 Browser launched (headed, session will close after task)")
    return _browser


def _get_llm() -> ChatGoogle:
    """Create the Gemini LLM instance for browser-use."""
    return ChatGoogle(
        model="gemini-2.0-flash",
        api_key=cfg.GEMINI_API_KEY,
        temperature=0.3,
        max_output_tokens=8096,
    )


async def run_browser_agent(
    task: str,
    on_step: Callable[[str, dict, int], Awaitable[None]] | None = None,
) -> str:
    """
    Run a browser-use Agent to complete a task in a real browser.

    The agent will:
      1. Open the browser (visible to the user)
      2. Navigate to relevant websites
      3. Fill forms, click buttons, scroll, extract data
      4. Return the final result as text

    Args:
        task: Natural language description of what to do.
              e.g. "Find flights from Belgrade to Ljubljana on Google Flights"
        on_step: Optional async callback(summary, action, step_number) for
                 progress updates sent to the frontend.

    Returns:
        A string summary of what the agent did and any extracted data.
    """
    log.info(f"🤖 Browser agent starting task: {task}")

    browser = await _get_browser()
    llm = _get_llm()

    # Step callback for progress reporting
    async def step_callback(state, output, step_num):
        try:
            action_names = []
            if output and hasattr(output, "action") and output.action:
                for a in output.action:
                    if a:
                        for field_name in a.model_fields_set:
                            action_names.append(field_name)

            summary = f"Step {step_num}"
            if action_names:
                summary += f": {', '.join(action_names)}"

            current_url = ""
            if state and hasattr(state, "url"):
                current_url = state.url or ""

            log.info(f"  📍 {summary} | url={current_url}")

            if on_step:
                await on_step(summary, {"url": current_url, "actions": action_names}, step_num)

        except Exception as e:
            log.warning(f"Step callback error: {e}")

    # Extra instructions so the agent handles popups/banners/overlays
    _POPUP_INSTRUCTIONS = (
        "\n\nIMPORTANT — POPUP & BANNER HANDLING:\n"
        "Before doing ANYTHING on a new page, ALWAYS check for and dismiss:\n"
        "  1. Cookie consent banners → click 'Accept all', 'Accept', 'Agree', 'OK', 'Got it'\n"
        "  2. Newsletter/email signup popups → click 'X', 'Close', 'No thanks', 'Maybe later'\n"
        "  3. Notification permission dialogs → click 'Block' or 'No thanks'\n"
        "  4. Login/signup overlays → click 'X', 'Close', 'Skip', 'Continue as guest'\n"
        "  5. Ad overlays or interstitials → click 'X', 'Close', 'Skip ad'\n"
        "  6. Location/language selection → pick English or the relevant option and proceed\n"
        "If an overlay or modal blocks the page, dismiss it FIRST before interacting with page content.\n"
        "If you can't find a close button, try pressing Escape or clicking outside the popup.\n"
        "\n"
        "THOROUGH SEARCH — DO NOT PICK THE FIRST RESULT:\n"
        "When searching for products, deals, flights, or any comparison task:\n"
        "  - Scroll down past the first few results to see more options.\n"
        "  - Sort results by price (low to high) when available.\n"
        "  - Compare at least 5-10 results before deciding what to report.\n"
        "  - Note the price, seller/source, ratings, and shipping costs.\n"
        "  - If prices seem too good to be true, flag them as potentially suspicious.\n"
        "  - Report the TOP options, not just the first one.\n"
    )

    try:
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            use_vision=True,
            max_actions_per_step=5,
            max_failures=5,
            register_new_step_callback=step_callback,
            extend_system_message=_POPUP_INSTRUCTIONS,
        )

        # Prevent the agent from killing the browser when it finishes,
        # but properly stop the event bus without triggering zombie respawns
        original_close = agent.close
        async def _safe_close():
            if agent.browser_session:
                # Temporarily pretend keep_alive=True so it doesn't kill the browser
                agent.browser_session.browser_profile.keep_alive = True
                await original_close()
                # Restore keep_alive=False so if the user closes it manually, it stays dead
                agent.browser_session.browser_profile.keep_alive = False
        agent.close = _safe_close

        result = await agent.run()

        # Extract the final result text
        if result and hasattr(result, "final_result") and result.final_result:
            final_text = result.final_result()
            log.info(f"✅ Browser agent completed. Result: {str(final_text)[:200]}")
            return str(final_text)
        elif result and hasattr(result, "history") and result.history:
            actions_taken = []
            for item in result.history[-5:]:
                if hasattr(item, "result") and item.result:
                    for r in item.result:
                        if hasattr(r, "extracted_content") and r.extracted_content:
                            actions_taken.append(r.extracted_content)
            if actions_taken:
                return "Browser task completed. " + " | ".join(actions_taken)

        return "Browser task completed successfully. The browser is showing the results."

    except Exception as e:
        log.error(f"❌ Browser agent error: {e}")
        return f"Browser automation error: {e}"


async def close_browser():
    """Cleanup browser resources."""
    global _browser
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
        log.info("Browser closed")


def resync_profile():
    """Delete the cached JARVIS profile so it gets re-copied from Brave next launch."""
    marker = Path(_JARVIS_PROFILE_DIR, _BRAVE_PROFILE, ".jarvis_synced")
    if marker.exists():
        marker.unlink()
        log.info("🔄 Profile sync marker cleared — will re-sync on next browser launch")
