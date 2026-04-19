"""
JARVIS — Lightweight Web Tools

Tools that answer common questions WITHOUT opening a browser:
  - get_weather:  Current weather + forecast via Open-Meteo (free, no API key)
  - web_search:   Quick Google search results via scraping

These exist so Gemini doesn't need to spin up a browser for simple queries.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import cfg

log = logging.getLogger("jarvis.tools.web")

# ── WMO Weather Codes → human description ────────────────────
_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


async def get_weather(
    location: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> str:
    """
    Get current weather + 3-day forecast using Open-Meteo (free, no key needed).
    
    If lat/lon not given, uses the default from config (user's home location).
    If a different location name is given, geocode it first.
    """
    try:
        # Determine coordinates
        if lat is not None and lon is not None:
            latitude, longitude = lat, lon
            place_name = location or f"{lat}, {lon}"
        elif location and location.lower() != cfg.LOCATION.lower():
            # Geocode the requested location
            geo = await _geocode(location)
            if geo is None:
                return f"Could not find location: {location}"
            latitude, longitude, place_name = geo
        else:
            latitude = cfg.LATITUDE
            longitude = cfg.LONGITUDE
            place_name = cfg.LOCATION

        # Fetch weather from Open-Meteo
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                    "timezone": "auto",
                    "forecast_days": 3,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Parse current weather
        cur = data["current"]
        current_desc = _WMO_CODES.get(cur["weather_code"], "Unknown")
        
        result = (
            f"📍 Weather for {place_name}:\n\n"
            f"🌡️ Now: {cur['temperature_2m']}°C (feels like {cur['apparent_temperature']}°C)\n"
            f"🌤️ {current_desc}\n"
            f"💨 Wind: {cur['wind_speed_10m']} km/h\n"
            f"💧 Humidity: {cur['relative_humidity_2m']}%\n"
        )

        # Parse forecast
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        if dates:
            result += "\n📅 Forecast:\n"
            for i, date in enumerate(dates):
                code = daily["weather_code"][i]
                desc = _WMO_CODES.get(code, "Unknown")
                hi = daily["temperature_2m_max"][i]
                lo = daily["temperature_2m_min"][i]
                rain = daily["precipitation_sum"][i]
                wind = daily["wind_speed_10m_max"][i]
                result += (
                    f"  {date}: {desc}, {lo}°C – {hi}°C"
                    f"{f', rain {rain}mm' if rain > 0 else ''}"
                    f", wind {wind} km/h\n"
                )

        return result

    except httpx.HTTPStatusError as e:
        log.error(f"Weather API error: {e}")
        return f"Weather API error: {e.response.status_code}"
    except Exception as e:
        log.error(f"Weather failed: {e}")
        return f"Could not fetch weather: {e}"


async def _geocode(location: str) -> Optional[tuple[float, float, str]]:
    """Geocode a location name → (lat, lon, display_name) using Open-Meteo geocoding."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": location, "count": 1, "language": "en"},
            )
            resp.raise_for_status()
            data = resp.json()
        
        results = data.get("results", [])
        if not results:
            return None
        
        r = results[0]
        name = r.get("name", location)
        country = r.get("country", "")
        display = f"{name}, {country}" if country else name
        return (r["latitude"], r["longitude"], display)
    
    except Exception as e:
        log.error(f"Geocoding failed for '{location}': {e}")
        return None


async def web_search(query: str) -> str:
    """
    Quick web search using DuckDuckGo Lite.
    Returns top 5 results with title, snippet, and URL.
    Good for quick factual lookups without opening a full browser.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                headers=headers,
            )
            resp.raise_for_status()
            html = resp.text

        results = _parse_ddg_lite(html)
        
        if not results:
            return f"No search results found for: {query}"
        
        output = f"🔍 Search results for '{query}':\n\n"
        for i, r in enumerate(results[:5], 1):
            output += f"{i}. {r['title']}\n"
            if r.get("snippet"):
                output += f"   {r['snippet']}\n"
            if r.get("url"):
                output += f"   🔗 {r['url']}\n"
            output += "\n"
        
        return output

    except Exception as e:
        log.error(f"Web search failed: {e}")
        return f"Search failed: {e}"


def _parse_ddg_lite(html: str) -> list[dict]:
    """Parse DuckDuckGo Lite HTML results."""
    import re
    
    results = []
    
    # DDG Lite puts results in <td> tags in groups of 4:
    #   1. number + title link
    #   2. snippet text  
    #   3. URL display
    #   4. empty separator
    # Extract all non-empty td contents
    tds = re.findall(r'<td[^>]*>(.*?)</td>', html, re.DOTALL)
    
    # Clean and filter meaningful tds
    cleaned = []
    for td in tds:
        text = re.sub(r'<[^>]+>', '', td).strip()
        # Clean HTML entities
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&#x27;', "'").replace('&quot;', '"')
        text = re.sub(r'&#x[0-9a-fA-F]+;', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if text and len(text) > 2:
            cleaned.append(text)
    
    # DDG Lite results come in triplets: title, snippet, url
    # Detect URL-like entries and group backwards
    i = 0
    while i < len(cleaned):
        # Skip date-only entries (e.g. "2026-03-10T00:00:00.0000000")
        if re.match(r'^\d{4}-\d{2}-\d{2}', cleaned[i]):
            i += 1
            continue
            
        # Look for a URL pattern (starts with a domain)
        # The pattern: title, then snippet, then URL line
        if i + 2 < len(cleaned):
            title = cleaned[i]
            snippet = cleaned[i + 1]
            url_candidate = cleaned[i + 2]
            
            # Check if url_candidate looks like a URL
            if re.match(r'^(https?://|www\.|\w+\.\w+/)', url_candidate):
                # Remove leading number from title if present (e.g. "1. Title")
                title = re.sub(r'^\d+\.\s*', '', title)
                
                # Clean trailing date from URL
                url = re.sub(r'\s+\d{4}-\d{2}-\d{2}.*$', '', url_candidate).strip()
                if not url.startswith('http'):
                    url = 'https://' + url
                
                results.append({
                    "title": title,
                    "snippet": snippet,
                    "url": url,
                })
                i += 3
                continue
        
        # If we have title + url (no snippet between)
        if i + 1 < len(cleaned):
            url_candidate = cleaned[i + 1]
            if re.match(r'^(https?://|www\.|\w+\.\w+/)', url_candidate):
                title = re.sub(r'^\d+\.\s*', '', cleaned[i])
                url = re.sub(r'\s+\d{4}-\d{2}-\d{2}.*$', '', url_candidate).strip()
                if not url.startswith('http'):
                    url = 'https://' + url
                results.append({
                    "title": title,
                    "snippet": "",
                    "url": url,
                })
                i += 2
                continue
        
        i += 1
    
    return results
