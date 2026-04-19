"""
JARVIS — Reminder / Scheduler

Fire-and-forget delayed tasks.
Currently supports: delayed Telegram reminders.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

log = logging.getLogger("jarvis.scheduler")

# Keep track of active reminders so they can be listed / cancelled later
_active_reminders: list[dict] = []


async def set_reminder(delay_seconds: int, message: str) -> str:
    """
    Schedule a Telegram message to be sent after *delay_seconds*.

    The function returns immediately (confirmation string).
    A background asyncio task handles the actual delay + send.
    """
    if delay_seconds < 5:
        delay_seconds = 5  # minimum 5 s to avoid instant-fire

    fire_at = datetime.now() + timedelta(seconds=delay_seconds)
    entry = {
        "message": message,
        "delay": delay_seconds,
        "fire_at": fire_at.isoformat(),
        "fired": False,
    }
    _active_reminders.append(entry)

    async def _fire():
        try:
            log.info(f"⏳ Reminder scheduled: {delay_seconds}s — \"{message[:60]}\"")
            await asyncio.sleep(delay_seconds)

            from clients.telegram_client import send_telegram_message
            await send_telegram_message(f"⏰ Reminder: {message}")

            entry["fired"] = True
            log.info(f"🔔 Reminder fired: \"{message[:60]}\"")
        except Exception as e:
            log.error(f"Reminder failed: {e}")

    # Schedule as a background task on the running event loop
    asyncio.create_task(_fire())

    # Human-friendly confirmation
    if delay_seconds < 60:
        human_time = f"{delay_seconds} seconds"
    elif delay_seconds < 3600:
        mins = delay_seconds // 60
        human_time = f"{mins} minute{'s' if mins != 1 else ''}"
    else:
        hrs = delay_seconds // 3600
        mins = (delay_seconds % 3600) // 60
        human_time = f"{hrs} hour{'s' if hrs != 1 else ''}"
        if mins:
            human_time += f" {mins} min"

    return (
        f"Reminder set. I will send you a Telegram notification in {human_time} "
        f"(at {fire_at.strftime('%H:%M')})."
    )
