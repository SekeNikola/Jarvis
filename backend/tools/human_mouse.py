"""
JARVIS — Human Mouse & Keyboard Automation

Simulates human-like input with:
- Bezier curve mouse movements
- Random overshoot & correction
- Variable typing speeds and natural pauses
"""

from __future__ import annotations

import logging
import math
import random
import time

import numpy as np
import pyautogui

log = logging.getLogger("jarvis.human_mouse")

# Disable pyautogui's default pause since we want precise human-like control
pyautogui.PAUSE = 0


def _cubic_bezier(t: float, p0: tuple, p1: tuple, p2: tuple, p3: tuple) -> tuple:
    u = 1 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t

    px = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    py = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    return px, py


def human_move(x: int, y: int, duration: float = None) -> None:
    """
    Human-like mouse movement using a bezier curve.
    Includes slight random offset and overshoot correction.
    """
    start_x, start_y = pyautogui.position()
    
    # Add random ±3px offset to final target
    target_x = x + random.randint(-3, 3)
    target_y = y + random.randint(-3, 3)
    
    distance = math.hypot(target_x - start_x, target_y - start_y)
    
    # Calculate duration if not provided
    if duration is None:
        if distance < 10:
            duration = random.uniform(0.1, 0.2)
        else:
            duration = min(max(distance / 1000.0, 0.3), 1.0) + random.uniform(0.1, 0.3)
    
    if distance < 5:
        pyautogui.moveTo(target_x, target_y, duration=duration, tween=pyautogui.easeInOutQuad)
        return

    # Generate control points for the bezier curve
    dev = max(distance * 0.2, 10)  # deviation magnitude
    
    cp1_x = start_x + (target_x - start_x) * random.uniform(0.2, 0.4) + random.uniform(-dev, dev)
    cp1_y = start_y + (target_y - start_y) * random.uniform(0.2, 0.4) + random.uniform(-dev, dev)
    
    cp2_x = start_x + (target_x - start_x) * random.uniform(0.6, 0.8) + random.uniform(-dev, dev)
    cp2_y = start_y + (target_y - start_y) * random.uniform(0.6, 0.8) + random.uniform(-dev, dev)
    
    steps = int(max(duration * 60, 10))
    
    # Optional overshoot
    overshoot = random.random() < 0.3
    if overshoot:
        overshoot_x = target_x + random.uniform(-10, 10)
        overshoot_y = target_y + random.uniform(-10, 10)
        steps_main = int(steps * 0.8)
        steps_corr = steps - steps_main
    else:
        steps_main = steps
        steps_corr = 0
        overshoot_x, overshoot_y = target_x, target_y
    
    # Move main part
    for i in range(1, steps_main + 1):
        t = i / steps_main
        t = math.sin(t * math.pi / 2) # ease out
        
        px, py = _cubic_bezier(t, (start_x, start_y), (cp1_x, cp1_y), (cp2_x, cp2_y), (overshoot_x, overshoot_y))
        pyautogui.moveTo(px, py)
        time.sleep(duration / steps)
        
    # Move correction part if overshot
    if overshoot:
        time.sleep(random.uniform(0.05, 0.15))
        for i in range(1, steps_corr + 1):
            t = i / steps_corr
            t = math.sin(t * math.pi / 2)
            
            px = overshoot_x + (target_x - overshoot_x) * t
            py = overshoot_y + (target_y - overshoot_y) * t
            pyautogui.moveTo(px, py)
            time.sleep((duration * 0.2) / max(steps_corr, 1))


def human_click(x: int, y: int, button: str = "left") -> None:
    """Move to (x,y) and click human-like."""
    human_move(x, y)
    
    time.sleep(random.uniform(0.08, 0.20))
    pyautogui.mouseDown(button=button)
    time.sleep(random.uniform(0.05, 0.12))
    pyautogui.mouseUp(button=button)
    
    log.info(f"👆 Human clicked at ({x}, {y})")


def human_double_click(x: int, y: int) -> None:
    """Move to (x,y) and double click human-like."""
    human_move(x, y)
    time.sleep(random.uniform(0.08, 0.20))
    
    pyautogui.mouseDown(button="left")
    time.sleep(random.uniform(0.05, 0.10))
    pyautogui.mouseUp(button="left")
    
    time.sleep(random.uniform(0.05, 0.15))
    
    pyautogui.mouseDown(button="left")
    time.sleep(random.uniform(0.05, 0.10))
    pyautogui.mouseUp(button="left")
    
    log.info(f"👆👆 Human double-clicked at ({x}, {y})")


def human_right_click(x: int, y: int) -> None:
    """Move to (x,y) and right click human-like."""
    human_click(x, y, button="right")


def human_scroll(x: int, y: int, amount: int, direction: str = "down") -> None:
    """Scroll in small increments with slight delays to mimic trackpad momentum."""
    human_move(x, y)
    time.sleep(random.uniform(0.1, 0.3))
    
    steps = abs(amount)
    sign = -1 if direction == "up" else 1
    
    log.info(f"↕️ Human scrolling {direction} {steps} steps")
    
    for i in range(steps):
        scroll_val = sign * random.randint(1, 3) 
        pyautogui.scroll(scroll_val)
        delay = 0.01 + (i / steps) * 0.05
        time.sleep(delay)


def human_type(text: str, wpm: int = 60) -> None:
    """Type text with random delay between keystrokes and occasional pauses."""
    base_delay = 1.0 / max(((wpm * 5) / 60), 1)
    
    log.info(f"⌨️ Human typing: '{text[:20]}{'...' if len(text) > 20 else ''}' at ~{wpm} wpm")
    
    for char in text:
        pyautogui.write(char)
        if char in ['.', ',', '!', '?', ';', ':']:
            time.sleep(random.uniform(0.2, 0.5))
        elif char == ' ':
            time.sleep(random.uniform(0.05, 0.15))
        else:
            time.sleep(max(0, random.gauss(base_delay, base_delay * 0.3)))
