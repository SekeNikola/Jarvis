"""
JARVIS — Gmail Tool (Read-Only)

Reads unread emails from Gmail using the Gmail API.
Read-only — no sending capability.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("jarvis.tools.email")

# Reuse the same credentials / token paths as calendar
_CREDS_DIR = Path(__file__).resolve().parent.parent
_CREDENTIALS_FILE = _CREDS_DIR / "credentials.json"
_TOKEN_FILE_GMAIL = _CREDS_DIR / "token_gmail.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_gmail_service():
    """Build and return an authenticated Gmail service."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None

    if _TOKEN_FILE_GMAIL.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE_GMAIL), SCOPES)

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

        _TOKEN_FILE_GMAIL.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _decode_body(payload: dict) -> str:
    """Extract plain text body from Gmail message payload."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    # Multipart — recurse through parts
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        # Check nested parts
        for subpart in part.get("parts", []):
            if subpart.get("mimeType") == "text/plain" and subpart.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(subpart["body"]["data"]).decode("utf-8", errors="replace")

    return "(no plain text body)"


async def get_emails(limit: int = 10, sender: Optional[str] = None) -> str:
    """
    Fetch recent unread emails from Gmail.
    Optionally filter by sender address.
    Returns a formatted string.
    """
    def _fetch() -> str:
        try:
            service = _get_gmail_service()

            # Build query
            query_parts = ["is:unread"]
            if sender:
                query_parts.append(f"from:{sender}")
            query = " ".join(query_parts)

            results = service.users().messages().list(
                userId="me",
                q=query,
                maxResults=limit,
            ).execute()

            messages = results.get("messages", [])
            if not messages:
                return "No unread emails found." + (f" (filter: from:{sender})" if sender else "")

            lines = [f"📧 Unread emails ({len(messages)}):\n"]

            for msg_meta in messages:
                msg = service.users().messages().get(
                    userId="me",
                    id=msg_meta["id"],
                    format="full",
                ).execute()

                headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
                subject = headers.get("subject", "(no subject)")
                from_addr = headers.get("from", "unknown")
                date = headers.get("date", "")

                # Get a preview of the body
                body = _decode_body(msg["payload"])
                preview = body[:200].replace("\n", " ").strip()
                if len(body) > 200:
                    preview += "…"

                lines.append(f"  ── {subject}")
                lines.append(f"     From: {from_addr}")
                lines.append(f"     Date: {date}")
                lines.append(f"     Preview: {preview}")
                lines.append("")

            return "\n".join(lines)

        except FileNotFoundError as e:
            return str(e)
        except Exception as e:
            log.error(f"Gmail error: {e}")
            return f"Error fetching emails: {e}"

    log.info(f"📧 Fetching emails (limit={limit}, sender={sender})")
    return await asyncio.to_thread(_fetch)
