"""
Push-to-talk audio recorder.
Requires optional dependencies: sounddevice, keyboard, numpy.
"""
from __future__ import annotations

import logging
import queue
from io import BytesIO
from typing import Optional
import wave

logger = logging.getLogger(__name__)


def _require_modules():
    try:
        import sounddevice  # type: ignore
        import keyboard  # type: ignore
        import numpy  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional deps
        raise RuntimeError(
            "Push-to-talk requires sounddevice, keyboard, and numpy. "
            "Install with: pip install sounddevice keyboard numpy"
        ) from exc
    return sounddevice, keyboard, numpy


def record_push_to_talk(
    hotkey: str = "ctrl",
    sample_rate: int = 16000,
    channels: int = 1,
    dtype: str = "int16",
    max_duration_sec: Optional[int] = 30,
) -> bytes:
    """
    Hold the hotkey to record; releasing stops recording.
    Returns WAV bytes.
    """
    sounddevice, keyboard, numpy = _require_modules()

    logger.info("Hold %s to record, release to stop. Ctrl+C to exit.", hotkey)
    keyboard.wait(hotkey)
    logger.info("Recording…")
    q: queue.Queue = queue.Queue()

    def callback(indata, frames, time, status):
        if status:
            logger.debug("Sounddevice status: %s", status)
        q.put(indata.copy())

    frames = []
    with sounddevice.InputStream(
        samplerate=sample_rate, channels=channels, dtype=dtype, callback=callback
    ):
        elapsed_frames = 0
        while keyboard.is_pressed(hotkey):
            try:
                data = q.get(timeout=0.1)
                frames.append(data)
                elapsed_frames += len(data)
                if max_duration_sec and elapsed_frames / sample_rate >= max_duration_sec:
                    logger.info("Max recording duration reached; stopping.")
                    break
            except queue.Empty:
                continue

    if not frames:
        logger.info("No audio captured.")
        return b""

    audio = numpy.concatenate(frames, axis=0)
    return _to_wav_bytes(audio, sample_rate, channels, dtype)


def _to_wav_bytes(audio, sample_rate: int, channels: int, dtype: str) -> bytes:
    bio = BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(_dtype_width(dtype))
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return bio.getvalue()


def _dtype_width(dtype: str) -> int:
    widths = {
        "int16": 2,
        "int32": 4,
        "float32": 4,
    }
    if dtype not in widths:
        raise ValueError(f"Unsupported dtype for WAV: {dtype}")
    return widths[dtype]
