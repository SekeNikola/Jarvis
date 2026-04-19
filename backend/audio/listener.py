"""
JARVIS — Whisper STT Listener

Captures microphone audio using sounddevice and transcribes it
locally with faster-whisper. No cloud dependency for voice input.

Usage (called from main.py in a thread):
    listener = WhisperListener()
    text = listener.listen_and_transcribe()
"""

from __future__ import annotations

import io
import logging
import threading
import wave
from typing import Optional

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from config import cfg

log = logging.getLogger("jarvis.listener")

# Audio config
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
SILENCE_THRESHOLD = 600       # RMS below this = silence (floor for adaptive)
SILENCE_DURATION = 1.5        # seconds of silence before we stop
MAX_RECORD_SECONDS = 20       # hard cap on recording length
PRE_SPEECH_BUFFER = 0.5       # seconds of audio to keep before speech starts
AMBIENT_SAMPLE_SECS = 0.3    # seconds to calibrate ambient noise level


class WhisperListener:
    """Mic → faster-whisper → text."""

    def __init__(self):
        self._model: Optional[WhisperModel] = None
        self._stop_event = threading.Event()
        self._is_listening = False

    @property
    def model(self) -> WhisperModel:
        """Lazy-load the Whisper model."""
        if self._model is None:
            log.info(f"Loading Whisper model: {cfg.WHISPER_MODEL}")
            self._model = WhisperModel(
                cfg.WHISPER_MODEL,
                device="auto",       # CUDA if available, else CPU
                compute_type="int8",  # fast + low memory
            )
            log.info("Whisper model loaded ✓")
        return self._model

    def listen_and_transcribe(self) -> str:
        """
        Blocking call: records from mic until silence or stop_event,
        then transcribes with Whisper.

        Returns the transcribed text (or empty string).
        """
        audio = self.record()
        if audio is None or len(audio) == 0:
            return ""
        return self.transcribe(audio)

    def record(self) -> Optional[np.ndarray]:
        """Record from mic with VAD.  Returns raw int16 audio or None."""
        self._stop_event.clear()
        self._is_listening = True
        try:
            return self._record()
        finally:
            self._is_listening = False

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe int16 audio to text (public wrapper)."""
        return self._transcribe(audio)

    def stop(self):
        """Signal the listener to stop recording."""
        self._stop_event.set()

    @property
    def is_listening(self) -> bool:
        return self._is_listening

    # ── Recording ─────────────────────────────────────────────
    def _record(self) -> Optional[np.ndarray]:
        """
        Record from mic with voice-activity detection.
        Uses adaptive silence threshold calibrated from ambient noise.
        Stops when:
          - Silence detected for SILENCE_DURATION seconds
          - stop_event is set
          - MAX_RECORD_SECONDS reached
        """
        log.info("🎤 Listening...")
        chunks: list[np.ndarray] = []
        silence_frames = 0
        speech_started = False
        frames_per_chunk = int(SAMPLE_RATE * 0.1)  # 100ms chunks
        silence_chunks_needed = int(SILENCE_DURATION / 0.1)
        max_chunks = int(MAX_RECORD_SECONDS / 0.1)
        ambient_chunks = int(AMBIENT_SAMPLE_SECS / 0.1)

        # Adaptive threshold — calibrated from ambient noise
        threshold = SILENCE_THRESHOLD
        ambient_rms_values: list[float] = []

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=frames_per_chunk,
            ) as stream:
                for chunk_idx in range(max_chunks):
                    if self._stop_event.is_set():
                        log.info("Recording stopped by signal")
                        break

                    data, overflowed = stream.read(frames_per_chunk)
                    if overflowed:
                        log.warning("Audio buffer overflow")

                    chunk = data.flatten()
                    rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

                    # Calibrate threshold from ambient noise (first few chunks)
                    if not speech_started and chunk_idx < ambient_chunks:
                        ambient_rms_values.append(rms)
                        if len(ambient_rms_values) == ambient_chunks:
                            ambient = float(np.mean(ambient_rms_values))
                            threshold = max(SILENCE_THRESHOLD, ambient * 3)
                            log.info(
                                f"Ambient RMS: {ambient:.0f} → "
                                f"threshold: {threshold:.0f}"
                            )

                    if rms > threshold:
                        speech_started = True
                        silence_frames = 0
                        chunks.append(chunk)
                    elif speech_started:
                        silence_frames += 1
                        chunks.append(chunk)  # keep recording through silence
                        if silence_frames >= silence_chunks_needed:
                            log.info("Silence detected — stopping")
                            break
                    else:
                        # Pre-speech: keep a small rolling buffer
                        chunks.append(chunk)
                        if len(chunks) > int(PRE_SPEECH_BUFFER / 0.1):
                            chunks.pop(0)

        except Exception as e:
            log.error(f"Recording error: {e}")
            return None

        if not chunks or not speech_started:
            log.info("No speech detected")
            return None

        audio = np.concatenate(chunks)
        duration = len(audio) / SAMPLE_RATE
        log.info(f"Recorded {duration:.1f}s of audio")
        return audio

    # Languages Whisper often confuses with Serbian
    _REMAP_TO_SERBIAN = {"ru", "uk", "bg", "mk", "sl"}  # Russian, Ukrainian, Bulgarian, Macedonian, Slovenian

    # ── Transcription ─────────────────────────────────────────
    def _transcribe(self, audio: np.ndarray) -> str:
        """Run faster-whisper on the recorded audio."""
        log.info("📝 Transcribing...")

        # faster-whisper expects float32 in [-1, 1]
        audio_float = audio.astype(np.float32) / 32768.0

        # First pass: auto-detect language (no initial_prompt to avoid bias)
        segments, info = self.model.transcribe(
            audio_float,
            beam_size=5,
            vad_filter=True,
        )

        detected_lang = getattr(info, 'language', 'unknown')

        # Whisper often misidentifies Serbian as Russian/Ukrainian/Bulgarian
        # because they all use Cyrillic script. Re-run forced as Serbian.
        if detected_lang in self._REMAP_TO_SERBIAN:
            log.info(f"Detected '{detected_lang}' — likely Serbian, re-transcribing as sr")
            segments, info = self.model.transcribe(
                audio_float,
                beam_size=5,
                language="sr",
                vad_filter=True,
            )
            detected_lang = "sr"

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        full_text = " ".join(text_parts).strip()
        log.info(f"Transcription ({detected_lang}): \"{full_text}\"")
        return full_text
