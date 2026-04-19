"""
JARVIS — Terminal Tool

Executes shell commands safely with:
  - Dangerous command blocking
  - Timeout protection
  - Output size limits
"""

from __future__ import annotations

import asyncio
import logging
import shlex

from config import cfg

log = logging.getLogger("jarvis.tools.terminal")

# Limits
COMMAND_TIMEOUT = 30  # seconds
MAX_OUTPUT_LENGTH = 10_000  # characters


async def run_terminal_command(command: str) -> str:
    """
    Execute a shell command and return stdout + stderr.
    Blocks dangerous commands.
    """
    command = command.strip()

    if not command:
        return "Error: Empty command"

    # ── Safety check ──────────────────────────────────────
    cmd_lower = command.lower()
    for dangerous in cfg.DANGEROUS_COMMANDS:
        if dangerous in cmd_lower:
            return (
                f"⚠️ Blocked: Command contains '{dangerous.strip()}' which is potentially destructive. "
                f"For safety, JARVIS won't execute this. Please run it manually if intended."
            )

    log.info(f"💻 Running: {command[:100]}")

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=None,  # uses current working directory
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=COMMAND_TIMEOUT,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: Command timed out after {COMMAND_TIMEOUT}s"

        output_parts = []

        if stdout:
            decoded = stdout.decode("utf-8", errors="replace").strip()
            if decoded:
                output_parts.append(decoded)

        if stderr:
            decoded = stderr.decode("utf-8", errors="replace").strip()
            if decoded:
                output_parts.append(f"[stderr]\n{decoded}")

        if proc.returncode != 0:
            output_parts.append(f"\n[exit code: {proc.returncode}]")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        # Truncate if too long
        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:MAX_OUTPUT_LENGTH] + f"\n... (truncated, {len(output)} chars total)"

        log.info(f"Command finished: exit={proc.returncode}, output={len(output)} chars")
        return output

    except Exception as e:
        log.error(f"Command execution error: {e}")
        return f"Error executing command: {e}"
