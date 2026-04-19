"""
JARVIS — Screen Watcher

Unified find-and-click interface.
Pipeline (try each in order, stop at first success):
1. Template match against /jarvis/templates/
2. Color+shape detection (parse color hints from description)
3. Text detection via OCR (extract quoted text from description)
4. Contour/shape analysis
5. Gemini Vision fallback
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from pathlib import Path

import cv2

from tools.human_mouse import human_click
from tools.screen_vision import (
    capture_region,
    capture_screen,
    find_button_shapes,
    find_by_ai_vision,
    find_by_color_and_shape,
    find_by_template,
    find_text_on_screen,
)
from config import cfg

log = logging.getLogger("jarvis.screen_watcher")

ROOT_DIR = Path(__file__).resolve().parent.parent

TEMPLATES_DIR = ROOT_DIR / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# Helper parsing
def _parse_color(description: str) -> tuple | None:
    desc = description.lower()
    if "blue" in desc: return (200, 120, 30) # BGR
    if "green" in desc: return (60, 180, 60)
    if "red" in desc: return (50, 50, 200)
    return None

def _extract_text(description: str) -> str | None:
    match = re.search(r'"([^"]+)"', description)
    if match: return match.group(1)
    match = re.search(r"'([^']+)'", description)
    if match: return match.group(1)
    
    match = re.search(r'(?:label|labeled|labeld|text)\s+([\w]+)', description, re.IGNORECASE)
    if match: return match.group(1)
    
    words = [w for w in description.split() if w.lower() not in ("click", "press", "button", "link", "icon", "the", "a", "an", "inside", "on", "in", "with", "blue", "red", "green", "vs", "code")]
    if words: return " ".join(words)
    return None

async def smart_find(description: str) -> tuple[int, int] | None:
    """Find an element on screen using a pipeline of methods."""
    log.info(f"🔍 smart_find: '{description}'")
    
    # 1. Template match
    safe_name = "".join(c for c in description.lower() if c.isalnum() or c in " -_").strip().replace(" ", "-")
    template_path = TEMPLATES_DIR / f"{safe_name}.png"
    if template_path.exists():
        log.info("Trying Method 1: Template match")
        res = find_by_template(str(template_path))
        if res: return res
        
    # Also check all templates if any matches the description name
    for t in TEMPLATES_DIR.glob("*.png"):
        if t.stem.replace("-", " ") in description.lower():
            log.info(f"Trying Method 1: Template match with {t.name}")
            res = find_by_template(str(t))
            if res: return res

# 2. Gemini Vision (Smart AI detection)
    # We skip OpenCV text/color heuristics because they blindly click text inside code editors
    # or chat windows. Gemini Vision understands context and UI elements natively.
    log.info("Trying Method 2: Gemini Vision")
    res = await find_by_ai_vision(description)
    if res: return res
    
    log.warning(f"❌ Failed to find '{description}' on screen")
    return None

async def smart_click(description: str, confirm: bool = False) -> bool:
    """Finds an element and clicks it, optionally asking for confirmation."""
    coords = await smart_find(description)
    if not coords:
        return False
        
    x, y = coords
    
    if confirm:
        log.info(f"Requires confirmation to click '{description}' at ({x},{y})")
        from clients.telegram_client import send_telegram_message
        await send_telegram_message(f"Please confirm: click '{description}' at ({x}, {y})? Send 'yes' or 'click' to proceed.")
        
        # We need a way to block and wait for a reply from Telegram. 
        # A simple hack: poll for 60 seconds looking for an approval event.
        # For this prototype, we'll just log and assume false if no framework is ready.
        # But let's simulate a 10s wait and auto-reject, since true interactivity needs more state.
        log.warning("Confirmation required, but interactive approval logic not fully implemented. Auto-rejecting.")
        return False
        
    log.info(f"Clicking '{description}' at ({x},{y})")
    
    from datetime import datetime
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_dir = ROOT_DIR / "logs" / "screens"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    before = capture_screen()
    cv2.imwrite(str(logs_dir / f"action_{now_str}_before.png"), before)
    
    human_click(x, y)
    
    await asyncio.sleep(0.5)
    after = capture_screen()
    cv2.imwrite(str(logs_dir / f"action_{now_str}_after.png"), after)
    
    log_file = ROOT_DIR / "logs" / "screen_actions.log"
    with open(log_file, "a") as f:
        f.write(f"{datetime.now()} | CLICK   | coords=({x},{y}) | description='{description}' | confirmed={confirm}\n")
        f.write(f"{datetime.now()} | RESULT  | screenshot_after=logs/screens/action_{now_str}_after.png\n")
        
    return True

_watchers = {}

def watch_for(description: str, interval: float = 1.0, auto_click: bool = False, timeout: int = 300) -> None:
    """Background thread polling screen."""
    
    if description in _watchers:
        log.warning(f"Already watching for '{description}'")
        return
        
    log.info(f"Starting watcher for '{description}' (auto_click={auto_click})")
    
    def _watch_loop():
        start_time = time.time()
        while time.time() - start_time < timeout:
            if description not in _watchers:
                break
                
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                coords = loop.run_until_complete(smart_find(description))
                loop.close()
                
                if coords:
                    log.info(f"Watcher found '{description}' at {coords}")
                    if auto_click:
                        human_click(coords[0], coords[1])
                    else:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        from clients.telegram_client import send_telegram_message
                        loop.run_until_complete(send_telegram_message(f"👀 Spotted: '{description}' on screen at {coords}"))
                        loop.close()
                    break
            except Exception as e:
                log.error(f"Watcher error: {e}")
                
            time.sleep(interval)
            
        _watchers.pop(description, None)
        log.info(f"Stopped watching for '{description}'")
        
    thread = threading.Thread(target=_watch_loop, daemon=True)
    _watchers[description] = thread
    thread.start()

def stop_watching(description: str = None) -> None:
    """Stop watchers."""
    if description:
        _watchers.pop(description, None)
    else:
        _watchers.clear()

def save_template(name: str, x: int, y: int, w: int, h: int) -> str:
    """Save a region as a template."""
    img = capture_region(x, y, w, h)
    
    safe_name = "".join(c for c in name.lower() if c.isalnum() or c in " -_").strip().replace(" ", "-")
    path = TEMPLATES_DIR / f"{safe_name}.png"
    cv2.imwrite(str(path), img)
    log.info(f"Saved template: {safe_name} at {path}")
    return f"Template saved as {safe_name}"

def list_templates() -> list[str]:
    return [p.stem for p in TEMPLATES_DIR.glob("*.png")]

def delete_template(name: str) -> str:
    safe_name = "".join(c for c in name.lower() if c.isalnum() or c in " -_").strip().replace(" ", "-")
    path = TEMPLATES_DIR / f"{safe_name}.png"
    if path.exists():
        path.unlink()
        return f"Deleted template: {safe_name}"
    return f"Template not found: {safe_name}"

def bootstrap_templates():
    """Auto-detect common buttons and save them as templates on first run."""
    log.info("Bootstrapping common templates...")
    from tools.screen_vision import pytesseract
    if not pytesseract:
        log.warning("pytesseract not installed, skipping template bootstrap")
        return

    common_buttons = ["Allow", "OK", "Continue", "Skip", "Cancel", "Keep", "Deny"]
    screen = capture_screen()
    img_rgb = cv2.cvtColor(screen, cv2.COLOR_BGR2RGB)
    try:
        data = pytesseract.image_to_data(img_rgb, output_type=pytesseract.Output.DICT)
    except Exception as e:
        log.warning(f"Bootstrap OCR failed: {e}")
        return

    for btn in common_buttons:
        for i in range(len(data['text'])):
            if int(data['conf'][i]) > 70 and btn.lower() in data['text'][i].lower():
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                # Expand box slightly to capture button borders
                pad = 10
                bx = max(0, x - pad)
                by = max(0, y - pad)
                bw = min(screen.shape[1] - bx, w + pad * 2)
                bh = min(screen.shape[0] - by, h + pad * 2)
                
                safe_name = f"{btn.lower()}-button"
                path = TEMPLATES_DIR / f"{safe_name}.png"
                if not path.exists():
                    img = capture_region(bx, by, bw, bh)
                    cv2.imwrite(str(path), img)
                    log.info(f"Saved template: {safe_name} (confidence {data['conf'][i]}%)")
