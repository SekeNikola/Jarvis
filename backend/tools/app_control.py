"""
JARVIS — Desktop App Control Tool (macOS)

Controls desktop applications using AppleScript / osascript:
  - Open / launch apps
  - Close / quit apps
  - Focus / activate apps (bring to front)
  - List running apps
  - Minimize / maximize / fullscreen windows
  - Get info about frontmost app
  - Type text into apps (clipboard + paste)
  - Press keyboard keys and shortcuts
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

log = logging.getLogger("jarvis.tools.app_control")

COMMAND_TIMEOUT = 10  # seconds


async def _run_osascript(script: str) -> str:
    """Run an AppleScript snippet via osascript and return stdout."""
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=COMMAND_TIMEOUT
        )
    except asyncio.TimeoutError:
        proc.kill()
        return "Error: AppleScript timed out"

    out = stdout.decode().strip()
    err = stderr.decode().strip()
    if proc.returncode != 0 and err:
        return f"Error: {err}"
    return out


async def _run_shell(cmd: str) -> str:
    """Run a shell command and return stdout."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=COMMAND_TIMEOUT
        )
    except asyncio.TimeoutError:
        proc.kill()
        return "Error: command timed out"
    return stdout.decode().strip()


def _sanitize(name: str) -> str:
    """Sanitize an app name for use in AppleScript strings."""
    # Escape backslashes first, then double-quotes
    return name.replace("\\", "\\\\").replace('"', '\\"')


async def check_and_request_permissions() -> None:
    """On macOS, checks and requests Accessibility and Screen Recording permissions."""
    import platform
    if platform.system() != "Darwin":
        return

    # Check Accessibility
    # Using AppleScript to check if GUI scripting is enabled
    script = (
        'tell application "System Events"\n'
        '  return UI elements enabled\n'
        'end tell'
    )
    res = await _run_osascript(script)
    if "false" in res.lower() or "error" in res.lower():
        log.warning("Accessibility permission is missing. Requesting...")
        # This will trigger the macOS permission dialog if we try to use System Events
        await _run_osascript('tell application "System Events" to keystroke ""')

    # Check Screen Recording
    # We can try to take a small screenshot with mss and see if it fails or returns a desktop wallpaper
    # (macOS Catalina+ returns just the desktop wallpaper if permission is denied, or might throw)
    try:
        import mss
        with mss.mss() as sct:
            sct.grab({"top": 0, "left": 0, "width": 10, "height": 10})
    except Exception as e:
        log.warning(f"Screen Recording permission might be missing: {e}")


# ── Public API ────────────────────────────────────────────────

async def control_app(action: str, app_name: str | None = None) -> str:
    """
    Control a desktop application on macOS.

    Actions:
      - open        : Launch / activate an app
      - close / quit: Quit an app gracefully
      - focus       : Bring an app's windows to front
      - minimize    : Minimize the frontmost window of an app
      - maximize    : Resize app window to fill the screen
      - fullscreen  : Toggle macOS native fullscreen
      - hide        : Hide an app
      - list        : List all visible running applications
      - frontmost   : Get info about the currently active app
    """
    action = action.lower().strip()
    log.info(f"🖥️  App control: action={action}, app={app_name}")

    # ── Actions that don't need an app name ───────────────
    if action == "list":
        return await _list_running_apps()

    if action == "frontmost":
        return await _get_frontmost_app()

    # ── Actions that need an app name ─────────────────────
    if not app_name:
        return "Error: app_name is required for this action."

    safe_name = _sanitize(app_name)

    if action == "open":
        return await _open_app(safe_name)

    elif action in ("close", "quit"):
        return await _quit_app(safe_name)

    elif action == "focus":
        return await _focus_app(safe_name)

    elif action == "minimize":
        return await _minimize_app(safe_name)

    elif action == "maximize":
        return await _maximize_app(safe_name)

    elif action == "fullscreen":
        return await _fullscreen_app(safe_name)

    elif action == "hide":
        return await _hide_app(safe_name)

    else:
        return (
            f"Unknown action: '{action}'. "
            f"Available: open, close, focus, minimize, maximize, fullscreen, hide, list, frontmost"
        )


# ── Implementations ──────────────────────────────────────────

async def _open_app(name: str) -> str:
    """Open (launch or activate) an application."""
    # 'open -a' is the most reliable way on macOS
    result = await _run_shell(f'open -a "{name}"')
    if result.startswith("Error"):
        # Try with osascript as fallback
        result2 = await _run_osascript(
            f'tell application "{name}" to activate'
        )
        if result2.startswith("Error"):
            return f"Could not open '{name}': {result}. {result2}"
    
    # Wait for the app to actually launch (up to 5 seconds)
    log.info(f"Waiting for {name} to launch...")
    for i in range(10):  # Check every 0.5 seconds for up to 5 seconds
        await asyncio.sleep(0.5)
        running = await _run_shell(f'pgrep -x "{name}" > /dev/null && echo "yes" || echo "no"')
        if running.strip() == "yes":
            log.info(f"✅ {name} is now running")
            await asyncio.sleep(1)  # Give it another second to fully load UI
            return f"✅ Opened {name}"
    
    # If we get here, the app is still launching but might take longer
    return f"⏳ {name} is launching (may still be loading)..."


async def _quit_app(name: str) -> str:
    """Gracefully quit an application."""
    result = await _run_osascript(
        f'tell application "{name}" to quit'
    )
    if result.startswith("Error"):
        return f"Could not quit '{name}': {result}"
    return f"✅ Quit {name}"


async def _focus_app(name: str) -> str:
    """Bring an application to the front."""
    result = await _run_osascript(
        f'tell application "{name}" to activate'
    )
    if result.startswith("Error"):
        return f"Could not focus '{name}': {result}"
    return f"✅ Focused {name}"


async def _minimize_app(name: str) -> str:
    """Minimize the frontmost window of an app."""
    script = (
        f'tell application "System Events"\n'
        f'  tell process "{name}"\n'
        f'    set miniaturized of front window to true\n'
        f'  end tell\n'
        f'end tell'
    )
    result = await _run_osascript(script)
    if result.startswith("Error"):
        # Fallback: try via the app itself
        result2 = await _run_osascript(
            f'tell application "{name}"\n'
            f'  set miniaturized of front window to true\n'
            f'end tell'
        )
        if result2.startswith("Error"):
            return f"Could not minimize '{name}': {result}"
    return f"✅ Minimized {name}"


async def _maximize_app(name: str) -> str:
    """Resize the frontmost window to fill the screen."""
    script = (
        f'tell application "{name}" to activate\n'
        f'delay 0.3\n'
        f'tell application "System Events"\n'
        f'  tell process "{name}"\n'
        f'    tell front window\n'
        f'      set position to {{0, 25}}\n'
        f'      set size to {{1920, 1055}}\n'
        f'    end tell\n'
        f'  end tell\n'
        f'end tell'
    )
    # Get actual screen size first
    screen_script = (
        'tell application "Finder"\n'
        '  set _b to bounds of window of desktop\n'
        '  return _b\n'
        'end tell'
    )
    bounds = await _run_osascript(screen_script)
    # Parse "0, 0, 2560, 1440" format
    try:
        parts = [int(x.strip()) for x in bounds.split(",")]
        w, h = parts[2], parts[3]
        script = (
            f'tell application "{name}" to activate\n'
            f'delay 0.3\n'
            f'tell application "System Events"\n'
            f'  tell process "{name}"\n'
            f'    tell front window\n'
            f'      set position to {{0, 25}}\n'
            f'      set size to {{{w}, {h - 25}}}\n'
            f'    end tell\n'
            f'  end tell\n'
            f'end tell'
        )
    except (ValueError, IndexError):
        pass  # Use the default 1920x1055

    result = await _run_osascript(script)
    if result.startswith("Error"):
        return f"Could not maximize '{name}': {result}"
    return f"✅ Maximized {name}"


async def _fullscreen_app(name: str) -> str:
    """Toggle macOS native fullscreen for an app."""
    script = (
        f'tell application "{name}" to activate\n'
        f'delay 0.5\n'
        f'tell application "System Events"\n'
        f'  keystroke "f" using {{control down, command down}}\n'
        f'end tell'
    )
    result = await _run_osascript(script)
    if result.startswith("Error"):
        return f"Could not toggle fullscreen for '{name}': {result}"
    return f"✅ Toggled fullscreen for {name}"


async def _hide_app(name: str) -> str:
    """Hide an application."""
    result = await _run_osascript(
        f'tell application "System Events" to set visible of process "{name}" to false'
    )
    if result.startswith("Error"):
        return f"Could not hide '{name}': {result}"
    return f"✅ Hidden {name}"


async def _list_running_apps() -> str:
    """List all visible (non-background) running applications."""
    script = (
        'tell application "System Events"\n'
        '  set appList to name of every process whose background only is false\n'
        '  set AppleScript\'s text item delimiters to "\\n"\n'
        '  return appList as text\n'
        'end tell'
    )
    result = await _run_osascript(script)
    if result.startswith("Error"):
        return f"Could not list apps: {result}"

    apps = [a.strip() for a in result.split("\n") if a.strip()]
    apps.sort(key=str.lower)
    return f"Running applications ({len(apps)}):\n" + "\n".join(f"  • {a}" for a in apps)

async def get_active_window_title() -> str:
    """Returns the title of the currently focused window."""
    script = (
        'tell application "System Events"\n'
        '  set _p to first process whose frontmost is true\n'
        '  try\n'
        '    set _name to name of front window of _p\n'
        '    return _name\n'
        '  on error\n'
        '    return ""\n'
        '  end try\n'
        'end tell'
    )
    result = await _run_osascript(script)
    if result.startswith("Error"):
        return ""
    return result.strip()

async def bring_window_to_front(title_contains: str) -> bool:
    """Find a window by partial title match and focus it."""
    # AppleScript to iterate all windows and focus the one matching the title
    script = (
        'tell application "System Events"\n'
        '  set _procs to every process whose background only is false\n'
        '  repeat with _p in _procs\n'
        '    try\n'
        '      set _wins to every window of _p\n'
        '      repeat with _w in _wins\n'
        '        if name of _w contains "{title}" then\n'
        '          set frontmost of _p to true\n'
        '          perform action "AXRaise" of _w\n'
        '          return "true"\n'
        '        end if\n'
        '      end repeat\n'
        '    end try\n'
        '  end repeat\n'
        '  return "false"\n'
        'end tell'
    )
    script = script.replace("{title}", _sanitize(title_contains))
    result = await _run_osascript(script)
    return result.strip() == "true"

async def _get_frontmost_app() -> str:
    """Get info about the currently active (frontmost) application."""
    script = (
        'tell application "System Events"\n'
        '  set _p to first process whose frontmost is true\n'
        '  set _name to name of _p\n'
        '  set _wins to name of every window of _p\n'
        '  set AppleScript\'s text item delimiters to "\\n"\n'
        '  return _name & "\\n---\\n" & (_wins as text)\n'
        'end tell'
    )
    result = await _run_osascript(script)
    if result.startswith("Error"):
        return f"Could not get frontmost app: {result}"

    parts = result.split("\n---\n", 1)
    app_name = parts[0].strip()
    windows = parts[1].strip() if len(parts) > 1 else "(no windows)"
    return f"Frontmost app: {app_name}\nWindows:\n{windows}"


# ── Keyboard / Typing ────────────────────────────────────────

# Map of friendly key names → AppleScript key code numbers
_KEY_CODES = {
    "return": 36, "enter": 36,
    "tab": 48,
    "escape": 53, "esc": 53,
    "space": 49,
    "delete": 51, "backspace": 51,
    "forward_delete": 117,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "home": 115, "end": 119,
    "page_up": 116, "page_down": 121,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
}

# Map modifier names → AppleScript modifier syntax
_MODIFIER_MAP = {
    "command": "command down", "cmd": "command down",
    "control": "control down", "ctrl": "control down",
    "option": "option down", "alt": "option down",
    "shift": "shift down",
}


async def type_text(text: str, app_name: str | None = None) -> str:
    """
    Type text into the currently focused app (or a specified app).
    Uses clipboard + Cmd+V paste for reliability with long/special text.
    """
    if not text:
        return "Error: no text provided."

    log.info(f"⌨️  Typing {len(text)} chars into {app_name or 'focused app'}")

    # Focus the app first if specified
    if app_name:
        safe_name = _sanitize(app_name)
        await _run_osascript(f'tell application "{safe_name}" to activate')
        # Give the app time to come to foreground and be ready
        await asyncio.sleep(1.0)

    # Put text on clipboard via pbcopy (no permissions needed)
    proc = await asyncio.create_subprocess_exec(
        "pbcopy",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate(input=text.encode("utf-8"))
    await asyncio.sleep(0.15)

    # Paste with Cmd+V via System Events (needs Accessibility permissions)
    result = await _run_osascript(
        'tell application "System Events"\n'
        '  keystroke "v" using {command down}\n'
        'end tell'
    )

    if result.startswith("Error"):
        if "assistive" in result.lower() or "accessibility" in result.lower() or "not allowed" in result.lower():
            return (
                "Error: Accessibility permission required. "
                "The user needs to grant Accessibility access to Terminal/Python in "
                "System Settings → Privacy & Security → Accessibility. "
                "Tell the user to do this manually — do NOT try to use browser_agent to fix this."
            )
        return f"Could not paste text: {result}"

    return f"✅ Typed {len(text)} characters into {app_name or 'focused app'}"


async def press_key(key: str, modifiers: str | None = None, app_name: str | None = None) -> str:
    """
    Press a keyboard key, optionally with modifiers.

    key: A key name (return, tab, escape, space, up, down, etc.) or a single character.
    modifiers: Comma-separated modifier names (command, control, option, shift).
    app_name: Optional app to focus first.
    """
    if not key:
        return "Error: no key provided."

    log.info(f"⌨️  Press key: {key} (modifiers={modifiers}) in {app_name or 'focused app'}")

    # Focus app first if specified
    if app_name:
        safe_name = _sanitize(app_name)
        await _run_osascript(f'tell application "{safe_name}" to activate')
        await asyncio.sleep(0.5)

    # Build modifier list for AppleScript
    mod_parts = []
    if modifiers:
        for m in modifiers.split(","):
            m = m.strip().lower()
            if m in _MODIFIER_MAP:
                mod_parts.append(_MODIFIER_MAP[m])

    mod_clause = ""
    if mod_parts:
        mod_clause = f" using {{{', '.join(mod_parts)}}}"

    key_lower = key.lower().strip()

    # Check if it's a named key (use key code)
    if key_lower in _KEY_CODES:
        code = _KEY_CODES[key_lower]
        script = (
            f'tell application "System Events"\n'
            f'  key code {code}{mod_clause}\n'
            f'end tell'
        )
    elif len(key) == 1:
        # Single character — use keystroke
        safe_key = key.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'tell application "System Events"\n'
            f'  keystroke "{safe_key}"{mod_clause}\n'
            f'end tell'
        )
    else:
        return f"Unknown key: '{key}'. Use a single character or a key name (return, tab, escape, up, down, etc.)"

    result = await _run_osascript(script)
    if result.startswith("Error"):
        if "assistive" in result.lower() or "accessibility" in result.lower() or "not allowed" in result.lower():
            return (
                "Error: Accessibility permission required. "
                "Tell the user to grant access in System Settings → Privacy & Security → Accessibility. "
                "Do NOT try to use browser_agent to fix this."
            )
        return f"Could not press key '{key}': {result}"

    display = key
    if modifiers:
        display = f"{modifiers}+{key}"
    return f"✅ Pressed {display}"


async def click_coordinates(x: int, y: int, app_name: str | None = None) -> str:
    """
    Click at specific screen coordinates. Useful for clicking buttons in apps.
    """
    log.info(f"🖱️  Click at ({x}, {y}) in {app_name or 'screen'}")

    if app_name:
        safe_name = _sanitize(app_name)
        await _run_osascript(f'tell application "{safe_name}" to activate')
        await asyncio.sleep(0.3)

    # Use cliclick if available, otherwise AppleScript
    result = await _run_shell(f'cliclick c:{x},{y} 2>/dev/null')
    if not result.startswith("Error"):
        return f"✅ Clicked at ({x}, {y})"

    # Fallback: use AppleScript + Python Quartz (not as reliable)
    script = (
        'tell application "System Events"\n'
        f'  click at {{{x}, {y}}}\n'
        'end tell'
    )
    result = await _run_osascript(script)
    if result.startswith("Error"):
        # Install cliclick suggestion
        return (
            f"Could not click at ({x}, {y}). "
            f"Consider installing cliclick: brew install cliclick"
        )
    return f"✅ Clicked at ({x}, {y})"
