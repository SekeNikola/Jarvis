"""JARVIS — Smart Browser Orchestrator

Tries each navigation method in order.
Stops at first success.
Logs which method was used and why.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
import json
import asyncio

from config import cfg

log = logging.getLogger("jarvis.tools.smart_browser")

@dataclass
class BrowserResult:
    success: bool
    data: Any
    method: str = ""
    error: str = ""
    
    def with_method(self, method: str) -> BrowserResult:
        self.method = method
        return self

@dataclass
class ParsedIntent:
    action: str
    site: str
    query: str
    filters: dict
    output_format: str

class SmartBrowser:
    """Orchestrates 3-layer browser navigation."""
    
    def __init__(self):
        # Local browser instance could be managed here if needed
        self.page = None
    
    async def parse_intent(self, voice_intent: str) -> ParsedIntent:
        """
        Use Gemini (text only, cheap) to parse voice command:
        "find cheap gopro on facebook marketplace under 100 euros"
        """
        log.info(f"Parsing intent for: {voice_intent}")
        from google import genai
        from google.genai import types
        
        prompt = f"""
        Extract structured action from voice command: "{voice_intent}"
        
        Respond ONLY with JSON:
        {{
          "action": "search_listings|buy_cheapest|form_fill|find_info",
          "site": "domain or page name", 
          "query": "search query if any",
          "filters": {{ "max_price": int or null, "currency": "EUR|USD" }},
          "output_format": "listings|plain_text|confirmation"
        }}
        """
        
        try:
            client = genai.Client(api_key=cfg.GEMINI_API_KEY)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt,
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
                
            log.info(f"Parsed intent: {data}")
            return ParsedIntent(
                action=data.get("action", "find_info"),
                site=data.get("site", ""),
                query=data.get("query", ""),
                filters=data.get("filters", {}),
                output_format=data.get("output_format", "plain_text")
            )
            
        except Exception as e:
            log.error(f"Intent parse failed: {e}")
            return ParsedIntent("find_info", "", voice_intent, {}, "plain_text")
            
    async def try_html_layer(self, parsed: ParsedIntent) -> BrowserResult:
        """Layer 1: HTML parse + Playwright (Fastest, cheapest)"""
        from tools.html_navigator import extract_listings, fast_page_load
        import importlib
        
        if not parsed.site or "marketplace" not in parsed.site.lower():
            # For now, only test FB marketplace or return False
            return BrowserResult(False, None)
            
        log.info(f"LAYER 1: Try HTML parse on {parsed.site}")
        
        # We need a headless Playwright instance for this layer to be fast
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                page = await browser.new_page()
                
                # Apply speed optimization
                await fast_page_load(page)
                
                # Navigate
                url = parsed.site
                if not url.startswith("http"):
                    url = f"https://{url}"
                    
                # For search, construct URL directly if possible
                if parsed.query and "facebook.com/marketplace" in url.lower():
                    url = f"https://www.facebook.com/marketplace/search/?query={parsed.query}"
                    
                log.info(f"Navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded")
                
                # Wait briefly for client rendering
                import asyncio
                await asyncio.sleep(2.0)
                
                # Try extraction
                results = await extract_listings(page, parsed.site)
                
                await browser.close()
                
                if results:
                    log.info(f"LAYER 1 SUCCESS: Extracted {len(results)} items")
                    return BrowserResult(True, results)
                else:
                    log.warning("LAYER 1 FAILED: Could not extract data")
                    return BrowserResult(False, None)
                    
        except Exception as e:
            log.warning(f"LAYER 1 ERROR: {e}")
            return BrowserResult(False, None, error=str(e))

    async def try_browser_use_layer(self, parsed: ParsedIntent, voice_intent: str) -> BrowserResult:
        """Layer 2: Browser-Use with Gemini (Smart, multi-step)"""
        from tools.browser_use_navigator import browser_use_execute
        
        log.info(f"LAYER 2: Try browser-use for '{voice_intent}'")
        
        # Construct a clear task for the browser-use agent
        task = f"Go to {parsed.site} and find {parsed.query}"
        if parsed.filters.get("max_price"):
            task += f" under {parsed.filters['max_price']} {parsed.filters.get('currency', 'EUR')}"
            
        try:
            result_text = await browser_use_execute(task)
            if "error" not in result_text.lower():
                log.info("LAYER 2 SUCCESS")
                return BrowserResult(True, result_text)
            else:
                log.warning("LAYER 2 FAILED: Returned error")
                return BrowserResult(False, None, error=result_text)
        except Exception as e:
            log.warning(f"LAYER 2 ERROR: {e}")
            return BrowserResult(False, None, error=str(e))

    async def try_vision_layer(self, parsed: ParsedIntent, voice_intent: str) -> BrowserResult:
        """Layer 3: Vision fallback (Always works, but manual)"""
        from tools.vision_navigator import vision_navigate
        
        log.info(f"LAYER 3: Vision fallback for '{voice_intent}'")
        
        instruction = f"I need to navigate to {parsed.site} and search for {parsed.query}. Click the relevant search bar or link."
        try:
            success = await vision_navigate(instruction)
            if success:
                log.info("LAYER 3 SUCCESS")
                return BrowserResult(True, "Clicked element via Vision fallback")
            else:
                log.warning("LAYER 3 FAILED")
                return BrowserResult(False, None)
        except Exception as e:
            log.warning(f"LAYER 3 ERROR: {e}")
            return BrowserResult(False, None, error=str(e))

    async def execute(self, voice_intent: str) -> BrowserResult:
        """Execute the 3-layer pipeline."""
        log.info(f"INTENT   | {voice_intent}")
        
        # Parse intent
        parsed = await self.parse_intent(voice_intent)
        log.info(f"PARSED   | site={parsed.site} query={parsed.query} max_price={parsed.filters.get('max_price')}")
        
        # Layer 1: try HTML
        import time
        t0 = time.time()
        result = await self.try_html_layer(parsed)
        if result.success:
            log.info(f"LAYER 1  | html_parse -> SUCCESS ({time.time() - t0:.1f}s)")
            return result.with_method("html")
            
        # Layer 2: try browser-use
        t0 = time.time()
        result = await self.try_browser_use_layer(parsed, voice_intent)
        if result.success:
            log.info(f"LAYER 2  | browser_use -> SUCCESS ({time.time() - t0:.1f}s)")
            return result.with_method("browser-use")
            
        # Layer 3: vision fallback
        t0 = time.time()
        result = await self.try_vision_layer(parsed, voice_intent)
        if result.success:
            log.info(f"LAYER 3  | vision -> SUCCESS ({time.time() - t0:.1f}s)")
            return result.with_method("vision")
            
        log.error("ALL NAVIGATION LAYERS FAILED")
        return BrowserResult(False, None, "none", "All layers failed to execute intent")

async def format_results(raw_result: Any, intent: ParsedIntent) -> str:
    """
    Format results for voice output — concise, speakable.
    """
    if not raw_result:
        return "I couldn't find anything matching your request."
        
    if isinstance(raw_result, str):
        return f"I found some information: {raw_result[:200]}"
        
    if isinstance(raw_result, list) and len(raw_result) > 0 and isinstance(raw_result[0], dict):
        count = len(raw_result)
        item_name = intent.query if intent.query else "items"
        
        res = f"Found {count} {item_name}. "
        if count > 0:
            res += "Top options: "
            for i, item in enumerate(raw_result[:3]):
                title = item.get("title", f"Item {i+1}")
                price = item.get("price", "unknown price")
                # Truncate long titles
                if len(title) > 30:
                    title = title[:27] + "..."
                res += f"{title} for {price}. "
                
        res += "Want me to open any of them?"
        return res
        
    return str(raw_result)[:200]
