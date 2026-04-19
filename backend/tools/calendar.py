"""
JARVIS — Google Calendar Tool (Read-Only)

Reads upcoming events from Google Calendar using the Google Calendar API.
Requires OAuth2 credentials (credentials.json + token.json).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("jarvis.tools.calendar")

# Credentials path (in backend dir)
_CREDS_DIR = Path(__file__).resolve().parent.parent
_CREDENTIALS_FILE = _CREDS_DIR / "credentials.json"
_TOKEN_FILE = _CREDS_DIR / "token.json"

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _get_calendar_service():
    """Build and return an authenticated Google Calendar service."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None

    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Google credentials not found at {_CREDENTIALS_FILE}. "
                    f"Download credentials.json from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        _TOKEN_FILE.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


async def get_calendar_events(days: int = 7) -> str:
    """
    Fetch upcoming calendar events for the next N days.
    Returns a formatted string.
    """
    def _fetch() -> str:
        try:
            service = _get_calendar_service()

            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=days)).isoformat()

            events_result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=20,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = events_result.get("items", [])

            if not events:
                return f"No events found in the next {days} days."

            lines = [f"📅 Upcoming events ({days} days):\n"]
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date", ""))
                summary = event.get("summary", "Untitled")
                location = event.get("location", "")

                # Parse datetime for nice display
                try:
                    if "T" in start:
                        dt = datetime.fromisoformat(start)
                        when = dt.strftime("%a %b %d, %I:%M %p")
                    else:
                        when = start  # all-day event
                except Exception:
                    when = start

                line = f"  • {when} — {summary}"
                if location:
                    line += f" 📍 {location}"
                lines.append(line)

            return "\n".join(lines)

        except FileNotFoundError as e:
            return str(e)
        except Exception as e:
            log.error(f"Calendar error: {e}")
            return f"Error fetching calendar: {e}"

    log.info(f"📅 Fetching calendar events ({days} days)")
    return await asyncio.to_thread(_fetch)
