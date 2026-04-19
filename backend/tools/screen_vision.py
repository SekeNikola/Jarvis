"""
JARVIS — OpenCV Screen Automation Engine

Primary engine for UI element detection.
Fast, instant, and free. Falls back to Gemini Vision if needed.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path

import cv2
import mss
import numpy as np
from PIL import Image

try:
    import pytesseract
    from thefuzz import process as fuzz_process
except ImportError:
    pytesseract = None
    fuzz_process = None

log = logging.getLogger("jarvis.screen_vision")

# ── Screenshot Engine ─────────────────────────────────────────

def capture_screen() -> np.ndarray:
    """Capture the full primary screen as an OpenCV BGR image."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor
        screenshot = sct.grab(monitor)
        # Convert to numpy array (BGRA)
        img = np.array(screenshot)
        # Convert BGRA to BGR
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

def get_screen_scale() -> float:
    """Returns the scale factor between physical pixels and logical coordinates."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        return screenshot.size.width / monitor["width"]


def capture_region(x: int, y: int, w: int, h: int) -> np.ndarray:
    """Capture a specific region of the screen."""
    with mss.mss() as sct:
        monitor = {"top": y, "left": x, "width": w, "height": h}
        screenshot = sct.grab(monitor)
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def capture_active_window() -> np.ndarray:
    """
    Capture just the active window.
    For simplicity, we currently just capture the full screen.
    Getting active window bounds reliably cross-platform requires extra deps.
    """
    return capture_screen()


# ── OpenCV Detection Methods ──────────────────────────────────

def find_by_template(template_path: str, threshold: float = 0.85) -> tuple[int, int] | None:
    """Method 1: Template matching for known buttons/icons."""
    if not Path(template_path).exists():
        log.warning(f"Template not found: {template_path}")
        return None
        
    screen = capture_screen()
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        log.warning(f"Failed to load template: {template_path}")
        return None

    # Perform template matching
    res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

    if max_val >= threshold:
        h, w = template.shape[:2]
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        
        # Scale back to logical coordinates for PyAutoGUI
        scale = get_screen_scale()
        logical_x = int(center_x / scale)
        logical_y = int(center_y / scale)
        
        log.info(f"Template matched with confidence {max_val:.2f} at raw ({center_x}, {center_y}) -> logical ({logical_x}, {logical_y})")
        return (logical_x, logical_y)
        
    return None


def find_by_color_and_shape(
    color_bgr: tuple, 
    color_tolerance: int = 20,
    min_width: int = 40,
    min_height: int = 15,
    max_width: int = 300,
    aspect_ratio_range: tuple = (1.5, 8.0)
) -> list[tuple[int, int]]:
    """Method 2: Find button-shaped rectangles of a specific color."""
    screen = capture_screen()
    
    # Define color range
    lower_bound = np.array([
        max(0, color_bgr[0] - color_tolerance),
        max(0, color_bgr[1] - color_tolerance),
        max(0, color_bgr[2] - color_tolerance)
    ])
    upper_bound = np.array([
        min(255, color_bgr[0] + color_tolerance),
        min(255, color_bgr[1] + color_tolerance),
        min(255, color_bgr[2] + color_tolerance)
    ])
    
    # Create mask for color
    mask = cv2.inRange(screen, lower_bound, upper_bound)
    
    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    results = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if h == 0:
            continue
            
        aspect_ratio = w / float(h)
        
        if (min_width <= w <= max_width) and (h >= min_height) and \
           (aspect_ratio_range[0] <= aspect_ratio <= aspect_ratio_range[1]):
            # It's a button-shaped rectangle matching the color
            center_x = x + w // 2
            center_y = y + h // 2
            
            # Scale to logical coordinates
            scale = get_screen_scale()
            logical_x = int(center_x / scale)
            logical_y = int(center_y / scale)
            
            results.append((logical_x, logical_y))
            
    # Return sorted by size (largest first)
    return results


def find_button_shapes(min_area: int = 500) -> list[dict]:
    """Method 3: Canny edge detection + contour analysis."""
    screen = capture_screen()
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    
    # Blur and edge detection
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    
    # Morphological closing to connect edges
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    buttons = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
            
        # Approximate contour to polygon
        epsilon = 0.04 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        
        # Look for rectangles
        if len(approx) >= 4:
            x, y, w, h = cv2.boundingRect(cnt)
            if h == 0:
                continue
            aspect_ratio = w / float(h)
            
            # Buttons are usually wider than tall
            if 1.5 <= aspect_ratio <= 8.0:
                scale = get_screen_scale()
                logical_x = int((x + w // 2) / scale)
                logical_y = int((y + h // 2) / scale)
                buttons.append({
                    "x": int(x / scale), "y": int(y / scale),
                    "w": int(w / scale), "h": int(h / scale),
                    "center_x": logical_x,
                    "center_y": logical_y
                })
                
    return buttons


def find_text_on_screen(text: str, fuzzy: bool = True) -> tuple[int, int] | None:
    """Method 4: Text detection with pytesseract."""
    if pytesseract is None or fuzz_process is None:
        log.warning("pytesseract or thefuzz not available for text detection.")
        return None
        
    screen = capture_screen()
    img_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    
    try:
        data = pytesseract.image_to_data(img_gray, output_type=pytesseract.Output.DICT)
    except Exception as e:
        log.warning(f"Tesseract OCR failed: {e}")
        return None
        
    n_boxes = len(data['text'])
    if n_boxes == 0:
        return None

    # Create a list of all found words with their bounding boxes
    found_words = []
    for i in range(n_boxes):
        if int(data['conf'][i]) > 60:
            word_text = data['text'][i].strip()
            if word_text:
                found_words.append({
                    "text": word_text,
                    "x": data['left'][i],
                    "y": data['top'][i],
                    "w": data['width'][i],
                    "h": data['height'][i],
                })

    if not found_words:
        return None
        
    # Use fuzzy matching to find the best match
    word_choices = [word['text'] for word in found_words]
    
    # fuzz_process.extractOne returns (best_match_string, score)
    best_match = fuzz_process.extractOne(text, word_choices)
    
    if best_match and best_match[1] > 90:  # Use a confidence score of 90
        log.info(f"Fuzzy text match found: '{best_match[0]}' with score {best_match[1]} for query '{text}'")
        # Find the original word dict to get coordinates
        for word in found_words:
            if word['text'] == best_match[0]:
                raw_x = word['x'] + word['w'] // 2
                raw_y = word['y'] + word['h'] // 2
                
                # Scale back to logical
                scale = get_screen_scale()
                logical_x = int(raw_x / scale)
                logical_y = int(raw_y / scale)
                
                log.info(f"Fuzzy text match found: '{best_match[0]}' at raw ({raw_x}, {raw_y}) -> logical ({logical_x}, {logical_y})")
                return (logical_x, logical_y)

    log.warning(f"No suitable text match found for '{text}'. Best attempt: '{best_match[0]}' ({best_match[1]} score).")
    return None


# ── Fallback ──────────────────────────────────────────────────

async def find_by_ai_vision(description: str) -> tuple[int, int] | None:
    """Method 5: Gemini Vision fallback."""
    log.info("OpenCV failed, using Gemini Vision fallback")
    
    from config import cfg
    from google import genai
    from google.genai import types

    screen = capture_screen()
    # Convert BGR to RGB, then to PIL Image, then to base64
    img_rgb = cv2.cvtColor(screen, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    
    # Resize if too large
    max_dim = 800
    w, h = pil_img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG", optimize=True)
    b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")
    
    client = genai.Client(api_key=cfg.GEMINI_API_KEY)
    
    prompt = (
        f"Find the UI element: '{description}'. "
        "Return a JSON object with exact keys: "
        "{'found': bool, 'x': int, 'y': int, 'label': str, 'confidence': float}. "
        "The x and y should be the exact center coordinates of the button, icon, or element in pixels. "
        "CRITICAL: Do NOT select text inside a code editor, paragraph, or chat window unless explicitly asked. "
        "Look for actual interactive UI elements (buttons, tabs, inputs). "
        "If not found, set found to false."
    )
    
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")
            ]
        )
    ]
    
    try:
        # Use asyncio to thread it
        import asyncio
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=cfg.GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        
        text_resp = response.candidates[0].content.parts[0].text
        # Clean up possible markdown formatting
        text_resp = text_resp.strip()
        if text_resp.startswith("```json"):
            text_resp = text_resp[7:]
        if text_resp.startswith("```"):
            text_resp = text_resp[3:]
        if text_resp.endswith("```"):
            text_resp = text_resp[:-3]
            
        data = json.loads(text_resp)
        if isinstance(data, list):
            data = data[0] if len(data) > 0 else {}
            
        if data.get("found"):
            # The coordinates from Gemini are based on the (possibly resized) image we sent
            # `scale_back` translates Gemini coordinates to raw image coordinates
            # `logical_scale` translates raw image coordinates to PyAutoGUI logical points
            scale_back = max(w, h) / max_dim if max(w, h) > max_dim else 1.0
            logical_scale = get_screen_scale()
            
            raw_x = int(data.get("x", 0) * scale_back)
            raw_y = int(data.get("y", 0) * scale_back)
            
            logical_x = int(raw_x / logical_scale)
            logical_y = int(raw_y / logical_scale)
            
            log.info(f"Gemini Vision found element at raw ({raw_x}, {raw_y}) -> logical ({logical_x}, {logical_y}) with conf {data.get('confidence')}")
            return (logical_x, logical_y)
    except Exception as e:
        log.error(f"Gemini Vision fallback failed: {e}")
        
    return None