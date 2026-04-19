"""
JARVIS — Session Memory

Short-term conversation memory that persists for the current session only.
Resets on server restart (v1 — no persistent DB).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


MAX_MESSAGES = 20  # rolling window


@dataclass
class SessionMemory:
    """Holds the conversation history for one session."""

    _messages: list[dict] = field(default_factory=list)

    def add_user_message(self, text: str):
        self._messages.append({
            "role": "user",
            "content": text,
        })
        self._trim()

    def add_assistant_message(self, text: str):
        if text:
            self._messages.append({
                "role": "assistant",
                "content": text,
            })
            self._trim()

    def add_tool_result(self, tool_name: str, content: str):
        """Add a tool result as a user message (for context)."""
        self._messages.append({
            "role": "user",
            "content": f"[Tool result from {tool_name}]: {content}",
        })
        self._trim()

    def add_raw(self, message: dict):
        """Add a pre-formatted message (e.g. assistant with tool_use blocks)."""
        self._messages.append(message)
        self._trim()

    def get_messages(self) -> list[dict]:
        return list(self._messages)

    def clear(self):
        self._messages.clear()

    def _trim(self):
        if len(self._messages) > MAX_MESSAGES:
            self._messages = self._messages[-MAX_MESSAGES:]

    @property
    def count(self) -> int:
        return len(self._messages)
