"""JARVIS — Layer 2 Browser-Use Navigator

Integrates browser-use library with Gemini LLM for complex multi-step tasks.
Handles React SPAs, infinite scroll, login flows, multi-step forms.
"""

from __future__ import annotations

import logging
from browser_use import Agent as BrowserAgent
from browser_use.llm.google import ChatGoogle
from config import cfg

log = logging.getLogger("jarvis.tools.browser_use_navigator")

BROWSER_USE_TASKS = {
    "marketplace_search": """
        Go to facebook.com/marketplace.
        Search for: {query}
        Filter by location: Ljubljana, Slovenia
        Filter max price: {max_price} EUR if specified
        Extract first 10 listings: title, price, url
        Return as JSON list
    """,
    
    "buy_cheapest": """
        Search {site} for: {query}
        Sort by price ascending
        Return cheapest 5 results: title, price, url
        Do not click buy
    """,
    
    "form_fill": """
        Go to: {url}
        Fill form fields: {fields}
        Click submit button
        Return confirmation message or error
    """,
    
    "find_info": """
        Go to: {url}
        Find: {description}
        Return the information as plain text
    """,
}

async def browser_use_execute(task: str, browser_instance=None) -> str:
    """
    Hand off complex navigation tasks to browser-use.
    It handles: React SPAs, infinite scroll, login flows,
    multi-step forms, dynamic content.
    
    Use when: HTML parsing failed OR task has multiple steps
    """
    try:
        llm = ChatGoogle(
            model="gemini-2.0-flash",
            api_key=cfg.GEMINI_API_KEY,
            temperature=0.3,
            max_output_tokens=8096,
        )
        
        # We can pass an existing browser instance if needed, or let browser-use create one.
        kwargs = {}
        if browser_instance:
            kwargs["browser"] = browser_instance
            
        agent = BrowserAgent(
            task=task,
            llm=llm,
            use_vision=False,  # try without vision first (faster)
            **kwargs
        )
        
        result = await agent.run()
        
        # Extract the final result text
        if result and hasattr(result, "final_result") and result.final_result:
            final_text = result.final_result()
            log.info(f"✅ Browser-use task completed. Result: {str(final_text)[:200]}")
            return str(final_text)
        elif result and hasattr(result, "history") and result.history:
            actions_taken = []
            for item in result.history[-5:]:
                if hasattr(item, "result") and item.result:
                    for r in item.result:
                        if hasattr(r, "extracted_content") and r.extracted_content:
                            actions_taken.append(r.extracted_content)
            if actions_taken:
                return "Browser task completed. " + " | ".join(actions_taken)
                
        return "Browser task completed successfully."
        
    except Exception as e:
        log.error(f"❌ Browser-use execution failed: {e}")
        return f"Browser automation error: {e}"