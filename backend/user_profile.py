"""
JARVIS — User Profile (Persistent Memory)

Stores everything JARVIS knows about the user in a JSON file.
This is the AI's long-term memory — it persists across restarts.

Categories:
  - accounts:   Email, social, streaming accounts with which is default
  - contacts:   People the user frequently interacts with
  - routines:   Daily habits, work schedule, preferences
  - facts:      Learned facts about the user (AI can add these automatically)
  - work:       Job title, company, projects
  - locations:  Home, office, frequently visited places

The AI has a tool (learn_user_fact) to automatically add new facts
when it learns something about the user during conversation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.user_profile")

_PROFILE_FILE = Path(__file__).resolve().parent.parent / "user_profile.json"

# ── Default empty profile ─────────────────────────────────────
_DEFAULT_PROFILE: dict[str, Any] = {
    "accounts": {
        "email": [
            # {"address": "user@gmail.com", "provider": "gmail", "default": True, "label": "personal"},
        ],
        "messaging": [
            # {"platform": "telegram", "username": "@user", "default": True},
        ],
        "social": [
            # {"platform": "instagram", "username": "@user"},
        ],
        "streaming": [
            # {"platform": "spotify", "username": "user", "default": True},
        ],
    },
    "contacts": [
        # {"name": "Mom", "relation": "mother", "phone": "+381...", "email": "...", "notes": "prefers WhatsApp"},
    ],
    "work": {
        "title": "",
        "company": "",
        "field": "",
        "projects": [],       # current projects
        "skills": [],         # programming languages, tools
    },
    "routines": {
        "wake_time": "",      # e.g. "07:00"
        "sleep_time": "",     # e.g. "23:00"
        "work_hours": "",     # e.g. "09:00-17:00"
        "morning_routine": "",  # free text
        "commute": "",          # e.g. "drive to office, 20 min"
        "workout": "",          # e.g. "gym at 18:00 MWF"
    },
    "locations": {
        "home": "",           # full address or description
        "office": "",
        "favorites": [],      # ["IKEA Belgrade", "Cafe Central"]
    },
    "facts": [
        # Auto-learned facts from conversations:
        # {"fact": "User is allergic to peanuts", "learned_at": "2025-06-15T10:30:00", "source": "conversation"},
        # {"fact": "User prefers dark mode", "learned_at": "...", "source": "conversation"},
    ],
}


def _load() -> dict:
    """Load user profile from disk, merging with defaults for missing keys."""
    if _PROFILE_FILE.exists():
        try:
            saved = json.loads(_PROFILE_FILE.read_text(encoding="utf-8"))
            # Deep merge: ensure all default keys exist
            return _deep_merge(_DEFAULT_PROFILE, saved)
        except Exception as e:
            log.warning(f"Failed to load user profile: {e}")
    return json.loads(json.dumps(_DEFAULT_PROFILE))  # deep copy


def _save(profile: dict) -> None:
    """Persist profile to disk."""
    _PROFILE_FILE.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info(f"User profile saved → {_PROFILE_FILE}")


def _deep_merge(default: dict, override: dict) -> dict:
    """Recursively merge override into default (override wins)."""
    result = {}
    for key in set(list(default.keys()) + list(override.keys())):
        if key in override and key in default:
            if isinstance(default[key], dict) and isinstance(override[key], dict):
                result[key] = _deep_merge(default[key], override[key])
            else:
                result[key] = override[key]
        elif key in override:
            result[key] = override[key]
        else:
            result[key] = default[key]
    return result


# ── Public API ────────────────────────────────────────────────

def get_profile() -> dict:
    """Return the full user profile."""
    return _load()


def update_profile(updates: dict) -> dict:
    """Deep-update the profile. Returns the full updated profile."""
    current = _load()
    merged = _deep_merge(current, updates)
    _save(merged)
    return merged


def add_email_account(address: str, provider: str = "", default: bool = False, label: str = "") -> dict:
    """Add an email account. If default=True, unset other defaults."""
    profile = _load()
    accounts = profile.setdefault("accounts", {}).setdefault("email", [])

    # Check if already exists
    for acc in accounts:
        if acc.get("address", "").lower() == address.lower():
            acc["provider"] = provider or acc.get("provider", "")
            acc["label"] = label or acc.get("label", "")
            if default:
                for a in accounts:
                    a["default"] = False
                acc["default"] = True
            _save(profile)
            return profile

    # Add new
    if default:
        for a in accounts:
            a["default"] = False

    accounts.append({
        "address": address,
        "provider": provider or _guess_provider(address),
        "default": default or len(accounts) == 0,  # first one is auto-default
        "label": label,
    })
    _save(profile)
    return profile


def add_contact(name: str, relation: str = "", phone: str = "", email: str = "", notes: str = "") -> dict:
    """Add or update a contact."""
    profile = _load()
    contacts = profile.setdefault("contacts", [])

    # Update existing
    for c in contacts:
        if c.get("name", "").lower() == name.lower():
            if relation:
                c["relation"] = relation
            if phone:
                c["phone"] = phone
            if email:
                c["email"] = email
            if notes:
                c["notes"] = notes
            _save(profile)
            return profile

    contacts.append({
        "name": name,
        "relation": relation,
        "phone": phone,
        "email": email,
        "notes": notes,
    })
    _save(profile)
    return profile


def learn_fact(fact: str, source: str = "conversation") -> dict:
    """Add a learned fact about the user. AI calls this automatically."""
    profile = _load()
    facts = profile.setdefault("facts", [])

    # Avoid duplicates (simple substring check)
    for f in facts:
        if f.get("fact", "").lower().strip() == fact.lower().strip():
            return profile  # already known

    facts.append({
        "fact": fact,
        "learned_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
    })
    _save(profile)
    log.info(f"📝 Learned new fact: {fact}")
    return profile


def remove_fact(fact_text: str) -> dict:
    """Remove a fact by matching text."""
    profile = _load()
    facts = profile.get("facts", [])
    profile["facts"] = [f for f in facts if f.get("fact", "").lower().strip() != fact_text.lower().strip()]
    _save(profile)
    return profile


def get_default_email() -> str | None:
    """Return the user's default email address."""
    profile = _load()
    for acc in profile.get("accounts", {}).get("email", []):
        if acc.get("default"):
            return acc.get("address")
    # Fallback to first
    emails = profile.get("accounts", {}).get("email", [])
    return emails[0]["address"] if emails else None


def get_profile_for_prompt() -> str:
    """
    Build a system-prompt block with everything the AI needs to know about the user.
    This is injected into the Gemini system prompt.
    """
    profile = _load()
    lines = []

    # ── Accounts ──
    emails = profile.get("accounts", {}).get("email", [])
    if emails:
        lines.append("USER'S EMAIL ACCOUNTS:")
        for acc in emails:
            default_tag = " ← DEFAULT" if acc.get("default") else ""
            label = f" ({acc['label']})" if acc.get("label") else ""
            lines.append(f"  • {acc['address']} [{acc.get('provider', '')}]{label}{default_tag}")
        lines.append("  When user says 'check my email' — use the DEFAULT account above.")
        lines.append("  Only ask which account if user explicitly mentions another one.")
        lines.append("")

    messaging = profile.get("accounts", {}).get("messaging", [])
    if messaging:
        lines.append("MESSAGING ACCOUNTS:")
        for acc in messaging:
            default_tag = " ← DEFAULT" if acc.get("default") else ""
            lines.append(f"  • {acc['platform']}: {acc.get('username', '')}{default_tag}")
        lines.append("")

    # ── Contacts ──
    contacts = profile.get("contacts", [])
    if contacts:
        lines.append("FREQUENTLY CONTACTED PEOPLE:")
        for c in contacts:
            parts = [c["name"]]
            if c.get("relation"):
                parts.append(f"({c['relation']})")
            if c.get("phone"):
                parts.append(f"📱 {c['phone']}")
            if c.get("email"):
                parts.append(f"✉ {c['email']}")
            if c.get("notes"):
                parts.append(f"— {c['notes']}")
            lines.append(f"  • {' '.join(parts)}")
        lines.append("  When user says 'message Mom' or 'email John', use the info above. Don't ask for details you already know.")
        lines.append("")

    # ── Work ──
    work = profile.get("work", {})
    if work.get("title") or work.get("company"):
        lines.append("WORK:")
        if work.get("title"):
            lines.append(f"  Title: {work['title']}")
        if work.get("company"):
            lines.append(f"  Company: {work['company']}")
        if work.get("field"):
            lines.append(f"  Field: {work['field']}")
        if work.get("projects"):
            lines.append(f"  Projects: {', '.join(work['projects'])}")
        if work.get("skills"):
            lines.append(f"  Skills: {', '.join(work['skills'])}")
        lines.append("")

    # ── Routines ──
    routines = profile.get("routines", {})
    routine_items = [(k, v) for k, v in routines.items() if v]
    if routine_items:
        lines.append("DAILY ROUTINES:")
        for k, v in routine_items:
            nice_key = k.replace("_", " ").title()
            lines.append(f"  • {nice_key}: {v}")
        lines.append("")

    # ── Locations ──
    locations = profile.get("locations", {})
    if locations.get("home") or locations.get("office"):
        lines.append("LOCATIONS:")
        if locations.get("home"):
            lines.append(f"  • Home: {locations['home']}")
        if locations.get("office"):
            lines.append(f"  • Office: {locations['office']}")
        if locations.get("favorites"):
            lines.append(f"  • Favorites: {', '.join(locations['favorites'])}")
        lines.append("")

    # ── Learned facts ──
    facts = profile.get("facts", [])
    if facts:
        lines.append("THINGS I KNOW ABOUT THE USER:")
        for f in facts:
            lines.append(f"  • {f['fact']}")
        lines.append("")

    # ── Auto-learn instruction ──
    lines.append(
        "AUTO-LEARN: When the user mentions personal info (a new email, a friend's name, "
        "an allergy, a preference, their job, etc.), use the learn_user_fact tool to remember it. "
        "Don't announce that you're saving it — just quietly learn and move on. "
        "Only save genuinely useful facts, not trivial conversation details."
    )

    return "\n".join(lines) if lines else ""


def _guess_provider(email: str) -> str:
    """Guess email provider from address."""
    domain = email.split("@")[-1].lower() if "@" in email else ""
    if "gmail" in domain:
        return "gmail"
    if "outlook" in domain or "hotmail" in domain or "live." in domain:
        return "outlook"
    if "yahoo" in domain:
        return "yahoo"
    if "icloud" in domain or "me.com" in domain:
        return "icloud"
    return domain
