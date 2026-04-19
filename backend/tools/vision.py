"""
JARVIS — Screen Vision Tool

Captures the screen using mss, returns base64 image.
When sent to Claude, the screenshot is provided as an image content block
so Claude's vision capabilities can analyze it.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging

import mss
from PIL import Image

log = logging.getLogger("jarvis.tools.vision")

# Max dimension to resize screenshots to (saves tokens)
MAX_DIMENSION = 800


async def take_screenshot() -> list[dict]:
    """
    Capture the primary monitor and return a Claude-compatible
    image content block (base64 PNG).

    Returns a list with a single image block for Claude vision.
    """
    def _capture() -> bytes:
        with mss.mss() as sct:
            # Grab the primary monitor (or all if only 1 exists)
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            screenshot = sct.grab(monitor)

            # Convert to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            # Resize if too large (saves API tokens)
            w, h = img.size
            if max(w, h) > MAX_DIMENSION:
                scale = MAX_DIMENSION / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            # Encode as PNG
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()

    log.info("📸 Capturing screenshot...")
    
    # Run in main thread to avoid macOS CoreGraphics background thread issues
    png_bytes = _capture()
    b64 = base64.standard_b64encode(png_bytes).decode("utf-8")
    log.info(f"Screenshot captured: {len(png_bytes) / 1024:.0f} KB")

    # Return as Claude image content block
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64,
            },
        }
    ]
