"""
JARVIS — Claude Brain

The AI core. Wraps the Anthropic API with:
  - System prompt
  - Tool definitions (function calling)
  - Automatic tool-execution loop
  - Async generator that yields events for the WebSocket layer
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

import anthropic

from config import cfg

log = logging.getLogger("jarvis.brain")


# ── Tool Definitions ──────────────────────────────────────────
TOOLS: list[dict] = [
    {
        "name": "take_screenshot",
        "description": "Capture the current screen. Returns a base64-encoded PNG image. Use this when you need to see what's on the user's screen.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or ~-relative file path.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and folders in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or ~-relative directory path.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_terminal_command",
        "description": "Execute a shell command and return stdout/stderr. Dangerous commands (rm, sudo, etc.) will be blocked.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run.",
                }
            },
            "required": ["command"],
        },
    },
    {
        "name": "open_browser",
        "description": "Open a URL in a browser via Playwright.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL to open.",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_search",
        "description": "Search Google and return the top results with titles and snippets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_note",
        "description": "Create a markdown note and save it to the user's Notes directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Note title (used as filename).",
                },
                "content": {
                    "type": "string",
                    "description": "Markdown content of the note.",
                },
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "get_weather",
        "description": (
            "Get current weather and 3-day forecast for any location. "
            "Uses free Open-Meteo API — no browser needed. "
            "If no location is specified, returns weather for the user's home location."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City or place name. Leave empty for user's home location.",
                },
            },
        },
    },
    {
        "name": "web_search",
        "description": (
            "Quick web search that returns top 5 results with titles, snippets, and URLs. "
            "Use for quick lookups, finding addresses, phone numbers, opening hours, news, etc. "
            "Only use browser_agent when you need to INTERACT with a website."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "set_reminder",
        "description": (
            "Set a delayed reminder. After the specified number of seconds, "
            "a Telegram notification will be sent to the user. "
            "Use this when the user says 'remind me in X minutes/hours'. "
            "The tool returns immediately with a confirmation — the actual "
            "notification fires later in the background."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "delay_seconds": {
                    "type": "integer",
                    "description": "Delay in seconds before sending the reminder (e.g. 120 for 2 minutes, 3600 for 1 hour).",
                },
                "message": {
                    "type": "string",
                    "description": "The reminder message text the user will receive.",
                },
            },
            "required": ["delay_seconds", "message"],
        },
    },
]


# ── System Prompt ─────────────────────────────────────────────
def _build_system_prompt() -> str:
    return (
        f"You are JARVIS, a personal AI assistant. You are direct, precise, and efficient.\n"
        f"Keep responses concise — you are speaking aloud, not writing an essay.\n"
        f"Never explain what you're about to do. Just do it.\n\n"
        f"CURRENT USER: {cfg.USERNAME}\n"
        f"LOCATION: Belgrade, Serbia (lat 44.8176, lon 20.4633)\n"
        f"Use this location as default for weather, nearby places, etc.\n\n"
        f"SMART TOOL ROUTING:\n"
        f"  1. YOUR OWN KNOWLEDGE (no tool): facts, math, conversions, advice\n"
        f"  2. get_weather: any weather question (instant, no browser)\n"
        f"  3. web_search: quick lookups, addresses, news, hours (no browser)\n"
        f"  4. browser_agent: ONLY for interactive tasks (booking, forms, email, shopping)\n"
        f"Current user: {cfg.USERNAME}"
    )


# ── Tool Executor ─────────────────────────────────────────────
async def _execute_tool(name: str, input_data: dict) -> str | list:
    """
    Dispatch a tool call to the appropriate handler.
    Returns a string result or a list (for image content).
    """
    try:
        if name == "take_screenshot":
            from tools.vision import take_screenshot
            return await take_screenshot()

        elif name == "read_file":
            from tools.filesystem import read_file
            return await read_file(input_data["path"])

        elif name == "list_directory":
            from tools.filesystem import list_directory
            return await list_directory(input_data["path"])

        elif name == "run_terminal_command":
            from tools.terminal import run_terminal_command
            return await run_terminal_command(input_data["command"])

        elif name == "open_browser":
            from tools.browser import open_browser
            return await open_browser(input_data["url"])

        elif name == "browser_search":
            from tools.browser import browser_search
            return await browser_search(input_data["query"])

        elif name == "create_note":
            from tools.filesystem import create_note
            return await create_note(input_data["title"], input_data["content"])

        elif name == "get_weather":
            from tools.web_search import get_weather
            return await get_weather(
                location=input_data.get("location"),
            )

        elif name == "web_search":
            from tools.web_search import web_search
            return await web_search(input_data["query"])

        elif name == "set_reminder":
            from tools.scheduler import set_reminder
            return await set_reminder(
                delay_seconds=int(input_data["delay_seconds"]),
                message=input_data["message"],
            )

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        log.error(f"Tool '{name}' failed: {e}")
        return f"Tool error: {e}"


# ── Claude Brain ──────────────────────────────────────────────
class ClaudeBrain:
    """
    Async interface to Claude with automatic tool-call loop.

    Usage:
        brain = ClaudeBrain()
        async for event in brain.chat(messages):
            # event is {"type": "...", ...}
    """

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
        self.system_prompt = _build_system_prompt()

    async def chat(self, messages: list[dict]) -> AsyncGenerator[dict, None]:
        """
        Send messages to Claude and yield events.

        Automatically handles the tool-use loop:
          1. Send messages → Claude responds
          2. If Claude wants to call tools → execute them
          3. Append tool results → send again
          4. Repeat until Claude gives a final text response

        Yields:
            {"type": "tool_call",    "tool": str, "input": dict}
            {"type": "tool_result",  "tool": str, "result": Any}
            {"type": "text_delta",   "text": str}
            {"type": "text_done",    "text": str}
        """
        working_messages = list(messages)
        max_iterations = 10  # safety limit for tool loops

        for _ in range(max_iterations):
            # Call Claude (synchronous client, run in thread)
            import asyncio
            response = await asyncio.to_thread(
                self.client.messages.create,
                model=cfg.CLAUDE_MODEL,
                max_tokens=cfg.CLAUDE_MAX_TOKENS,
                system=self.system_prompt,
                tools=TOOLS,
                messages=working_messages,
            )

            log.info(f"Claude stop_reason={response.stop_reason}, blocks={len(response.content)}")

            # Process response content blocks
            text_parts: list[str] = []
            tool_uses: list[dict] = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                    yield {"type": "text_delta", "text": block.text}

                elif block.type == "tool_use":
                    tool_uses.append({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            full_text = "".join(text_parts)

            # If no tool calls, we're done
            if response.stop_reason != "tool_use" or not tool_uses:
                yield {"type": "text_done", "text": full_text}
                return

            # ── Tool execution loop ──────────────────────────
            # Add Claude's response (with tool_use blocks) to messages
            working_messages.append({
                "role": "assistant",
                "content": [b.model_dump() for b in response.content],
            })

            # Execute each tool and collect results
            tool_results = []
            for tool in tool_uses:
                yield {
                    "type": "tool_call",
                    "tool": tool["name"],
                    "input": tool["input"],
                }

                result = await _execute_tool(tool["name"], tool["input"])

                yield {
                    "type": "tool_result",
                    "tool": tool["name"],
                    "result": result,
                }

                # Build tool_result content block
                if isinstance(result, list):
                    # Image or complex content (e.g., screenshot returns image blocks)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool["id"],
                        "content": result,
                    })
                else:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool["id"],
                        "content": str(result),
                    })

            # Add tool results as a user message and loop
            working_messages.append({
                "role": "user",
                "content": tool_results,
            })

        # If we hit max iterations, yield what we have
        yield {"type": "text_done", "text": full_text if text_parts else "I ran into a loop processing tools. Here's what I found so far."}
