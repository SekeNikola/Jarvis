"""
JARVIS — Filesystem Tools

Safe file operations using pathlib.
Includes: read_file, list_directory, create_note.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from config import cfg

log = logging.getLogger("jarvis.tools.filesystem")

# Safety: max file size we'll read (10 MB)
MAX_READ_SIZE = 10 * 1024 * 1024
# Max depth for directory listing
MAX_DEPTH = 3
MAX_ENTRIES = 200


def _resolve_path(raw: str) -> Path:
    """Expand ~ and resolve to absolute path."""
    return Path(raw).expanduser().resolve()


async def read_file(path: str) -> str:
    """Read file contents. Returns text content or error message."""
    def _read() -> str:
        p = _resolve_path(path)

        if not p.exists():
            return f"Error: File not found: {p}"

        if not p.is_file():
            return f"Error: Not a file: {p}"

        size = p.stat().st_size
        if size > MAX_READ_SIZE:
            return f"Error: File too large ({size / 1024 / 1024:.1f} MB). Max is {MAX_READ_SIZE / 1024 / 1024:.0f} MB."

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            log.info(f"Read file: {p} ({len(content)} chars)")
            return content
        except Exception as e:
            return f"Error reading file: {e}"

    return await asyncio.to_thread(_read)


async def list_directory(path: str) -> str:
    """List directory contents as a tree. Returns formatted string."""
    def _list() -> str:
        p = _resolve_path(path)

        if not p.exists():
            return f"Error: Path not found: {p}"

        if not p.is_dir():
            return f"Error: Not a directory: {p}"

        lines = [f"📁 {p}/"]
        count = 0

        def walk(directory: Path, prefix: str, depth: int):
            nonlocal count
            if depth > MAX_DEPTH or count > MAX_ENTRIES:
                return

            try:
                entries = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError:
                lines.append(f"{prefix}⛔ Permission denied")
                return

            for i, entry in enumerate(entries):
                if count > MAX_ENTRIES:
                    lines.append(f"{prefix}... ({len(entries) - i} more)")
                    break

                count += 1
                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                icon = "📁" if entry.is_dir() else "📄"

                name = entry.name
                if entry.is_dir():
                    name += "/"

                lines.append(f"{prefix}{connector}{icon} {name}")

                if entry.is_dir() and depth < MAX_DEPTH:
                    extension = "    " if is_last else "│   "
                    walk(entry, prefix + extension, depth + 1)

        walk(p, "", 0)
        log.info(f"Listed directory: {p} ({count} entries)")
        return "\n".join(lines)

    return await asyncio.to_thread(_list)


async def create_note(title: str, content: str) -> str:
    """Create a markdown note in the Notes directory."""
    def _create() -> str:
        notes_dir = cfg.NOTES_DIR
        notes_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
        if not safe_title:
            safe_title = f"note-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        filename = f"{safe_title}.md"
        filepath = notes_dir / filename

        # Add frontmatter
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_content = f"---\ntitle: {title}\ndate: {now}\n---\n\n{content}"

        filepath.write_text(full_content, encoding="utf-8")
        log.info(f"Created note: {filepath}")
        return f"Note saved: {filepath}"

    return await asyncio.to_thread(_create)
