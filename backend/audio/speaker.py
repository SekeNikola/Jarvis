"""
JARVIS — Google Cloud TTS Speaker

Streams text-to-speech audio from Google Cloud Text-to-Speech API.
Uses the same GEMINI_API_KEY — no extra setup needed.
Free tier: 4 million characters/month.

Falls back to Fish Audio if FISH_AUDIO_API_KEY is set.

Usage:
    speaker = TTSSpeaker()
    async for chunk in speaker.synthesize("Hello, world"):
        # chunk is raw audio bytes (mp3)
        play_audio(chunk)
"""

from __future__ import annotations

import base64
import logging
import platform
import asyncio
import tempfile
import shutil
import os
from typing import AsyncGenerator

import httpx
import aiofiles

from config import cfg

log = logging.getLogger("jarvis.speaker")

# Google TTS endpoint
GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
# Fish Audio endpoint (fallback)
FISH_TTS_URL = cfg.FISH_AUDIO_BASE_URL

# Max text length per TTS request (Google limit is 5000 bytes)
MAX_CHUNK_LEN = 4500

# Default Google voice — British RP male, refined JARVIS tone
GOOGLE_VOICE = {
    "languageCode": "en-GB",
    "name": "en-GB-News-K",      # British male — authoritative newsreader tone
    "ssmlGender": "MALE",
}


class TTSSpeaker:
    """Streaming TTS — macOS local `say` (primary) or Google Cloud TTS."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self.use_macos_tts = platform.system() == "Darwin"
        self.ffmpeg_path = shutil.which("ffmpeg")

        if self.use_macos_tts:
            log.info(f"🔊 Using local macOS TTS with voice: {cfg.MACOS_VOICE}")
            if not self.ffmpeg_path:
                log.warning("ffmpeg not found. Local TTS may fail or have incorrect format.")
        else:
            log.info("🔊 Using Google Cloud TTS")

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Convert text to speech and yield audio chunks.
        Uses local macOS TTS if available, otherwise falls back to Google.
        """
        if not text.strip():
            return

        if self.use_macos_tts:
            async for chunk in self._macos_tts(text):
                yield chunk
        elif cfg.GEMINI_API_KEY:
            async for chunk in self._google_tts(text):
                yield chunk
        else:
            log.warning("No TTS API key available and not on macOS — skipping TTS")
            return

    async def _macos_tts(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesize via local macOS `say` command and convert to MP3."""
        log.info(f"🔊 macOS TTS: \"{text[:60]}...\"" if len(text) > 60 else f"🔊 macOS TTS: \"{text}\"")

        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as aiff_file:
            aiff_path = aiff_file.name
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_file:
            mp3_path = mp3_file.name

        try:
            # Generate AIFF directly using `say`
            say_proc = await asyncio.create_subprocess_exec(
                "say",
                "-v", cfg.MACOS_VOICE,
                "-o", aiff_path,
                text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await say_proc.communicate()

            if say_proc.returncode != 0:
                log.error(f"`say` command failed with exit code {say_proc.returncode}: {stderr.decode()}")
                return

            # Convert AIFF to MP3 using ffmpeg
            ffmpeg_proc = await asyncio.create_subprocess_exec(
                self.ffmpeg_path,
                "-y",                   # Overwrite output file
                "-i", aiff_path,
                "-f", "mp3",
                "-b:a", "192k",
                mp3_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            ffmpeg_stdout, ffmpeg_stderr = await ffmpeg_proc.communicate()

            if ffmpeg_proc.returncode != 0:
                log.error(f"`ffmpeg` command failed with exit code {ffmpeg_proc.returncode}: {ffmpeg_stderr.decode()}")
                return

            import aiofiles
            # Send the entire MP3 file in one chunk
            async with aiofiles.open(mp3_path, "rb") as f:
                audio_data = await f.read()
                if audio_data:
                    yield audio_data

        finally:
            # Clean up the temporary files
            import os
            if os.path.exists(aiff_path):
                os.remove(aiff_path)
            if os.path.exists(mp3_path):
                os.remove(mp3_path)


    async def _google_tts(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesize via Google Cloud Text-to-Speech API."""
        log.info(f"🔊 Google TTS: \"{text[:60]}...\"" if len(text) > 60 else f"🔊 Google TTS: \"{text}\"")

        # Split long text into chunks
        chunks = _split_text(text, MAX_CHUNK_LEN)

        for chunk_text in chunks:
            payload = {
                "input": {"text": chunk_text},
                "voice": GOOGLE_VOICE,
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": 0.95,
                    "pitch": -2.0,
                },
            }

            try:
                resp = await self.client.post(
                    GOOGLE_TTS_URL,
                    params={"key": cfg.GEMINI_API_KEY},
                    json=payload,
                )

                if resp.status_code != 200:
                    log.error(f"Google TTS error {resp.status_code}: {resp.text[:200]}")
                    return

                data = resp.json()
                audio_b64 = data.get("audioContent", "")
                if audio_b64:
                    audio_bytes = base64.b64decode(audio_b64)
                    # Yield the complete MP3 — each yield must be a valid file
                    yield audio_bytes
                    log.info(f"Google TTS chunk done: {len(audio_bytes) / 1024:.1f} KB")

            except httpx.TimeoutException:
                log.error("Google TTS request timed out")
            except Exception as e:
                log.error(f"Google TTS error: {e}")

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


def _split_text(text: str, max_len: int) -> list[str]:
    """Split text at sentence boundaries to stay under max_len."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    # Split on sentence-ending punctuation
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_len:
            current = f"{current} {sentence}".strip() if current else sentence
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)

    return chunks if chunks else [text[:max_len]]
