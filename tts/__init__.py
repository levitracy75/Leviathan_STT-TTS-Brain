"""
Text-to-speech interfaces powered by ElevenLabs.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from config import load_settings
from .elevenlabs import (
    DEFAULT_MODEL,
    ElevenLabsClient,
    ElevenLabsConfig,
    play_audio_bytes,
    play_audio_stream,
)

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ID = "6vZmwtARjUveRB7xsRcW"
DEFAULT_STABILITY = 0.35
DEFAULT_SIMILARITY = 0.7
DEFAULT_SPEED = 0.9  # Slightly quicker than minimum


def speak(text: str, *, voice_id: Optional[str] = None, play: bool = True) -> bytes:
    """
    Synthesize speech using the non-streaming endpoint. Returns audio bytes.
    """
    client = _build_client(voice_id)
    audio = client.speak_to_bytes(text)
    if play:
        play_audio_bytes(audio, description="tts")
    return audio


def stream_speech(text: str, *, voice_id: Optional[str] = None, play: bool = True) -> Optional[Iterable[bytes]]:
    """
    Stream speech; when play=True audio is played as it arrives, otherwise chunks are returned.
    """
    client = _build_client(voice_id)
    chunks = client.stream_audio_chunks(text)
    if play:
        play_audio_stream(chunks)
        return None
    return chunks


def _build_client(voice_id: Optional[str] = None) -> ElevenLabsClient:
    settings = load_settings()
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is required. Set it in your .env.")

    resolved_voice = voice_id or settings.elevenlabs_voice_id or DEFAULT_VOICE_ID
    stability = (
        settings.elevenlabs_voice_stability
        if settings.elevenlabs_voice_stability is not None
        else DEFAULT_STABILITY
    )
    similarity = (
        settings.elevenlabs_voice_similarity
        if settings.elevenlabs_voice_similarity is not None
        else DEFAULT_SIMILARITY
    )
    speed = _clamp_speed(
        settings.elevenlabs_voice_speed if settings.elevenlabs_voice_speed is not None else DEFAULT_SPEED
    )

    config = ElevenLabsConfig(
        api_key=settings.elevenlabs_api_key,
        voice_id=resolved_voice,
        model_id=settings.elevenlabs_model_id or DEFAULT_MODEL,
        stability=stability,
        similarity_boost=similarity,
        speed=speed,
        optimize_streaming_latency=settings.elevenlabs_optimize_streaming_latency,
    )
    logger.debug(
        "Using ElevenLabs voice_id=%s model=%s stability=%s similarity=%s speed=%s",
        resolved_voice,
        config.model_id,
        config.stability,
        config.similarity_boost,
        config.speed,
    )
    return ElevenLabsClient(config)


def _clamp_speed(speed: float) -> float:
    """
    Clamp speed to ElevenLabs-supported range [0.7, 1.2].
    """
    min_speed, max_speed = 0.7, 1.2
    if speed < min_speed:
        logger.warning("ELEVENLABS_VOICE_SPEED=%.2f below minimum %.1f; clamping.", speed, min_speed)
        return min_speed
    if speed > max_speed:
        logger.warning("ELEVENLABS_VOICE_SPEED=%.2f above maximum %.1f; clamping.", speed, max_speed)
        return max_speed
    return speed
