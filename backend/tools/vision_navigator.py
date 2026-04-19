"""JARVIS — Layer 3 Vision Navigator Fallback

Only called when HTML parsing and browser-use fail. Takes screenshot,
sends to Gemini, gets coordinates, executes human_click.
"""

from __future__ import annotations

import logging
import json
import base64
import io
import asyncio
from PIL import Image

import cv2
from google import genai
from google.genai import types

from tools.screen_vision import capture_screen, get_screen_scale
from tools.human_mouse import human_click
from config import cfg

log = logging.getLogger("jarvis.tools.vision_navigator")

VISION_PROMPT = """
You are navigating a web browser. 
Screenshot attached.
Task: {instruction}

Respond ONLY with JSON:
{{
  "action": "click",
  "x": int,
  "y": int,
  "text": "string if typing",
  "element_description": "what you found",
  "confidence": 0.0-1.0
}}

If confidence < 0.7, set x and y to -1.
"""

async def vision_navigate(instruction: str) -> bool:
    """
    Take screenshot → send to Gemini Vision →
    get coordinates → human_click()
    Last resort only — logs reason layers 1+2 failed
    """
    log.info(f"Trying Vision Fallback Layer for: {instruction}")
    
    screen = capture_screen()
    # Convert BGR to RGB, then to PIL Image, then to base64
    img_rgb = cv2.cvtColor(screen, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    
    # Resize if too large
    max_dim = 1280
    w, h = pil_img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG", optimize=True)
    b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")
    
    client = genai.Client(api_key=cfg.GEMINI_API_KEY)
    prompt = VISION_PROMPT.format(instruction=instruction)
    
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
            
        confidence = data.get("confidence", 0.0)
        action = data.get("action")
        x = data.get("x", -1)
        y = data.get("y", -1)
        
        if confidence >= 0.7 and x >= 0 and y >= 0 and action == "click":
            # Scale back
            scale_back = max(w, h) / max_dim if max(w, h) > max_dim else 1.0
            logical_scale = get_screen_scale()
            
            raw_x = int(x * scale_back)
            raw_y = int(y * scale_back)
            
            logical_x = int(raw_x / logical_scale)
            logical_y = int(raw_y / logical_scale)
            
            log.info(f"Vision Fallback found element '{data.get('element_description')}' at raw ({raw_x}, {raw_y}) -> logical ({logical_x}, {logical_y}) with confidence {confidence}")
            human_click(logical_x, logical_y)
            return True
        else:
            log.warning(f"Vision Fallback low confidence ({confidence}) or invalid coordinates ({x}, {y})")
            return False
            
    except Exception as e:
        log.error(f"Vision Fallback error: {e}")
        
    return False