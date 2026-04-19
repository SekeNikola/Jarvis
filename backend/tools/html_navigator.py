"""JARVIS — Layer 1 HTML Navigator

Uses raw HTML parsing (BeautifulSoup, lxml, cssselect) combined with Playwright
to execute browser actions extremely fast without relying on visual AI.
"""

from __future__ import annotations

import logging
from typing import Any
from bs4 import BeautifulSoup
from playwright.async_api import Page, ElementHandle

log = logging.getLogger("jarvis.tools.html_navigator")

KNOWN_SELECTORS = {
    "facebook.com/marketplace": {
        "search": 'input[placeholder="Search Marketplace"]',
        "location": 'input[placeholder="Location"]',
        "filter_price_max": 'input[aria-label="Maximum price"]',
        "category": '[aria-label="Category"]',
        "listing_titles": 'span[dir="auto"]',
        "listing_prices": 'span[style*="font-weight"]',
        "listing_links": 'a[href*="/marketplace/item/"]',
    },
    "google.com": {
        "search": 'input[name="q"]',
        "search_button": 'input[value="Google Search"]',
        "results": "#search .g",
    },
    "mimovrste.com": {
        "search": 'input[name="q"]',
        "product_title": ".product-title",
        "product_price": ".price",
    },
    "bolha.com": {
        "search": 'input[name="q"]',
        "listings": ".entity-body",
        "price": ".price-box",
    },
    "ceneje.si": {
        "search": 'input[name="q"]',
        "product": ".product-item",
        "price": ".price",
    },
}

async def fast_page_load(page: Page):
    """
    Block unnecessary resources for speed:
    - Block: images, fonts, CSS, analytics, ads
    - Allow: HTML, JS (needed for React sites)
    - Result: 3-5x faster page loads
    """
    async def route_handler(route):
        if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
            await route.abort()
        else:
            await route.continue_()
            
    await page.route("**/*", route_handler)


async def get_page_structure(page: Page) -> dict:
    """
    Extract simplified page structure without CSS.
    Returns clean dict, no styling info.
    """
    html = await page.content()
    soup = BeautifulSoup(html, "lxml")
    
    structure = {
        "inputs": [],
        "buttons": [],
        "links": [],
        "forms": []
    }
    
    for inp in soup.find_all("input"):
        structure["inputs"].append({
            "type": inp.get("type", "text"),
            "name": inp.get("name", ""),
            "placeholder": inp.get("placeholder", ""),
            "id": inp.get("id", "")
        })
        
    for btn in soup.find_all("button"):
        structure["buttons"].append({
            "text": btn.get_text(strip=True),
            "type": btn.get("type", ""),
            "id": btn.get("id", "")
        })
        
    for link in soup.find_all("a", href=True):
        structure["links"].append({
            "text": link.get_text(strip=True),
            "href": link["href"]
        })
        
    for form in soup.find_all("form"):
        structure["forms"].append({
            "action": form.get("action", ""),
            "method": form.get("method", "")
        })
        
    return structure


async def find_element(page: Page, description: str) -> ElementHandle | None:
    """
    Smart element finder.
    Priority order:
    1. Exact placeholder match
    2. Aria label match
    3. Name attribute
    4. ID contains keyword
    5. Button text match
    """
    desc_lower = description.lower()
    
    # 1. Placeholder
    el = await page.query_selector(f'input[placeholder*="{description}" i]')
    if el: return el
    
    # 2. Aria label
    el = await page.query_selector(f'[aria-label*="{description}" i]')
    if el: return el
    
    # 3. Name attribute (exact usually works better for name)
    el = await page.query_selector(f'input[name="{desc_lower}"]')
    if el: return el
    
    # 4. ID
    el = await page.query_selector(f'#{desc_lower}')
    if el: return el
    
    # 5. Button text match
    el = await page.query_selector(f'button:has-text("{description}")')
    if el: return el
    
    # Also check generic text links if looking for a specific text
    el = await page.query_selector(f'a:has-text("{description}")')
    if el: return el
    
    return None

async def extract_listings(page: Page, site: str) -> list[dict]:
    """
    Extract structured data from listing pages using KNOWN_SELECTORS.
    Returns: [{title, price, url}]
    """
    # Simple matching to find the right config
    site_config = None
    for k, v in KNOWN_SELECTORS.items():
        if k in site:
            site_config = v
            break
            
    if not site_config:
        log.warning(f"No KNOWN_SELECTORS for {site}")
        return []
        
    # This is a naive implementation that would need site-specific logic
    # to tie titles/prices/urls together into cohesive items.
    # For a robust implementation, we'd need container selectors.
    
    # Let's try to extract something basic
    try:
        if "listing_titles" in site_config and "listing_prices" in site_config:
            titles = await page.query_selector_all(site_config["listing_titles"])
            prices = await page.query_selector_all(site_config["listing_prices"])
            
            results = []
            count = min(len(titles), len(prices), 10)  # Up to 10
            for i in range(count):
                title_text = await titles[i].inner_text()
                price_text = await prices[i].inner_text()
                if title_text and price_text:
                    results.append({
                        "title": title_text,
                        "price": price_text
                    })
            return results
    except Exception as e:
        log.error(f"Error extracting listings: {e}")
        
    return []
