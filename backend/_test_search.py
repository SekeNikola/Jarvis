import asyncio, httpx, re

async def test():
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": "flights Ljubljana to Belgrade"},
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        html = resp.text

        # Get exact classes
        result_classes = re.findall(r'<div class="(result[^"]*)"', html)
        print("Result div classes:", result_classes[:5])

        # Get hrefs
        hrefs = re.findall(r'class="result__a"[^>]*href="([^"]*)"', html)
        print("Hrefs:", hrefs[:3])

        # Get titles
        atags = re.findall(r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
        print("Titles:", [a.strip()[:60] for a in atags[:3]])

        # Get snippets
        snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:td|div|span)', html, re.DOTALL)
        print("Snippets:", [s.strip()[:80] for s in snips[:3]])

        # Print raw section around first result
        idx = html.find('result__a')
        if idx > 0:
            print("\n--- Raw around first result__a ---")
            print(html[idx-100:idx+300])

asyncio.run(test())
