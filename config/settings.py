"""
Settings loader for Leviathan.
Loads environment variables from .env and exposes a simple Settings object.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .env import get_env, load_env


@dataclass
class Settings:
    elevenlabs_api_key: str | None
    elevenlabs_voice_id: str | None
    elevenlabs_model_id: str | None
    elevenlabs_voice_stability: float | None
    elevenlabs_voice_similarity: float | None
    elevenlabs_voice_speed: float | None
    elevenlabs_optimize_streaming_latency: int | None
    openai_api_key: str | None
    openai_stt_model: str | None
    local_whisper_model: str | None
    llm_provider: str | None
    openai_llm_model: str | None
    ollama_model: str | None
    project_root: Path
    tts_playback_volume: float | None


def load_settings(dotenv_path: str | Path = ".env") -> Settings:
    load_env(dotenv_path)
    project_root = Path(get_env("PROJECT_ROOT", default=Path.cwd().as_posix()) or Path.cwd())
    return Settings(
        elevenlabs_api_key=get_env("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=get_env("ELEVENLABS_VOICE_ID"),
        elevenlabs_model_id=get_env("ELEVENLABS_MODEL_ID"),
        elevenlabs_voice_stability=_optional_float(get_env("ELEVENLABS_VOICE_STABILITY")),
        elevenlabs_voice_similarity=_optional_float(get_env("ELEVENLABS_VOICE_SIMILARITY")),
        elevenlabs_voice_speed=_optional_float(get_env("ELEVENLABS_VOICE_SPEED")),
        elevenlabs_optimize_streaming_latency=_optional_int(
            get_env("ELEVENLABS_OPTIMIZE_STREAMING_LATENCY")
        ),
        openai_api_key=get_env("OPENAI_API_KEY"),
        openai_stt_model=get_env("OPENAI_STT_MODEL"),
        local_whisper_model=get_env("LOCAL_WHISPER_MODEL"),
        llm_provider=(get_env("LLM_PROVIDER") or "local").lower(),
        openai_llm_model=get_env("OPENAI_LLM_MODEL"),
        ollama_model=get_env("OLLAMA_MODEL"),
        project_root=Path(project_root),
        tts_playback_volume=_optional_float(get_env("TTS_PLAYBACK_VOLUME")),
    )


def _optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        raise RuntimeError(f"Invalid float for setting: {value}")


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"Invalid integer for setting: {value}")
