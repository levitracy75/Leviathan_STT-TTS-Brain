"""
Minimal ElevenLabs client for speech synthesis.
Uses urllib to avoid external dependencies and ffplay (if present) for playback.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional

logger = logging.getLogger(__name__)

API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_MODEL = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_CHUNK_SIZE = 16 * 1024


@dataclass
class ElevenLabsConfig:
    api_key: str
    voice_id: str
    model_id: str = DEFAULT_MODEL
    stability: float = 0.35
    similarity_boost: float = 0.7
    speed: float | None = None  # 1.0 is default speed; lower slows speech.
    style: float | None = None
    use_speaker_boost: bool = True
    optimize_streaming_latency: int | None = None  # 0-4 where lower is lower latency
    output_format: str = DEFAULT_OUTPUT_FORMAT
    chunk_size: int = DEFAULT_CHUNK_SIZE

    def as_payload(self, text: str) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "use_speaker_boost": self.use_speaker_boost,
            },
        }
        if self.speed is not None:
            payload["voice_settings"]["speed"] = self.speed
        if self.style is not None:
            payload["voice_settings"]["style"] = self.style
        if self.optimize_streaming_latency is not None:
            payload["optimize_streaming_latency"] = self.optimize_streaming_latency
        if self.output_format:
            payload["output_format"] = self.output_format
        return payload


class ElevenLabsClient:
    def __init__(self, config: ElevenLabsConfig):
        self.config = config

    def speak_to_bytes(self, text: str) -> bytes:
        """
        Synthesize full audio and return bytes (non-streaming endpoint).
        """
        chunks = list(self._iter_request(text, stream=False))
        return b"".join(chunks)

    def stream_audio_chunks(self, text: str) -> Iterator[bytes]:
        """
        Stream audio chunks as they arrive from the streaming endpoint.
        """
        yield from self._iter_request(text, stream=True)

    def _iter_request(self, text: str, stream: bool) -> Iterator[bytes]:
        if not text:
            return
        endpoint = f"{API_BASE}/text-to-speech/{self.config.voice_id}"
        if stream:
            endpoint += "/stream"
        payload = json.dumps(self.config.as_payload(text)).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
            "xi-api-key": self.config.api_key,
        }
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                if not stream:
                    yield resp.read()
                    return
                while True:
                    chunk = resp.read(self.config.chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except urllib.error.HTTPError as err:
            body = ""
            try:
                body = err.read().decode("utf-8", errors="replace")
            except Exception:  # pragma: no cover - best effort logging
                body = "<unreadable error body>"
            raise RuntimeError(f"ElevenLabs request failed ({err.code}): {body}") from err
        except urllib.error.URLError as err:
            raise RuntimeError(f"ElevenLabs request failed: {err}") from err


def play_audio_bytes(data: bytes, description: str | None = None, volume: float | None = None) -> None:
    """
    Play audio bytes using ffplay when available; otherwise save to temp and log path.
    """
    if not data:
        logger.warning("No audio data to play%s", f" for {description}" if description else "")
        return

    ffplay = _ffplay_path()
    if ffplay:
        try:
            result = subprocess.run(
                _ffplay_command(ffplay, volume),
                input=data,
                check=False,
            )
            if result.returncode == 0:
                return
            logger.warning("ffplay exited with code %s; writing audio to a temp file", result.returncode)
        except FileNotFoundError:
            logger.debug("ffplay not found at playback time; will fallback to file write")
        except Exception as exc:
            logger.warning("ffplay playback failed: %s; writing audio to a temp file", exc)

    path = _write_temp_file(data)
    if not path:
        return

    played = _attempt_play_with_retries(path, volume=volume)
    if played:
        _safe_remove(path)
        return

    logger.warning("Audio saved to %s (auto-play unavailable; play manually)", path)


def play_audio_stream(chunks: Iterable[bytes], volume: float | None = None) -> None:
    """
    Stream audio through ffplay if available; otherwise buffer then play once.
    """
    ffplay = _ffplay_path()
    if not ffplay:
        buffered = b"".join(chunks)
        play_audio_bytes(buffered, volume=volume)
        return

    proc: subprocess.Popen | None = None
    command = _ffplay_command(ffplay, volume)
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
        )
        for chunk in chunks:
            if not chunk or not proc.stdin:
                continue
            try:
                proc.stdin.write(chunk)
            except BrokenPipeError:
                logger.warning("ffplay pipe closed early")
                break
        if proc.stdin:
            proc.stdin.close()
        proc.wait()
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait()


def _ffplay_path() -> Optional[str]:
    path = shutil.which("ffplay")
    if path:
        return path
    # Try common Windows install location
    candidates = [
        r"C:\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffplay.exe",
        r"C:\Program Files\ffmpeg\bin\ffplay.exe",
    ]
    for cand in candidates:
        if Path(cand).exists():
            return cand
    return None


def _ffplay_command(ffplay: str, volume: float | None = None) -> list[str]:
    volume_arg = _ffmpeg_volume_filter(volume)
    cmd = [ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet"]
    if volume_arg:
        cmd.extend(["-af", volume_arg])
    cmd.append("-")
    return cmd


def _ffmpeg_volume_filter(volume: float | None) -> Optional[str]:
    if volume is None:
        return None
    normalized = _normalize_volume(volume)
    return f"volume={normalized:.3f}"


def _normalize_volume(volume: float) -> float:
    if volume < 0:
        logger.warning("Requested volume %.3f is below 0; clamping to 0.", volume)
        return 0.0
    if volume > 2.0:
        logger.warning("Requested volume %.3f is above 2.0; clamping to 2.0.", volume)
        return 2.0
    return volume


def _volume_percent(volume: float | None) -> int:
    if volume is None:
        return 100
    normalized = _normalize_volume(volume)
    return max(0, min(int(round(normalized * 100)), 200))


def _afplay_volume(volume: float | None) -> Optional[str]:
    if volume is None:
        return None
    normalized = max(0.0, min(_normalize_volume(volume), 1.0))
    return f"{normalized:.2f}"


def _ffplay_available() -> bool:
    return _ffplay_path() is not None


def _write_temp_file(data: bytes) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp.write(data)
            return tmp.name
    except Exception as exc:  # pragma: no cover - only logs
        logger.error("Failed to write temp audio file: %s", exc)
        return None


def _auto_play_file(path: str, volume: float | None = None) -> bool:
    """
    Try to auto-play the saved file using platform tools.
    """
    if sys.platform.startswith("win"):
        wm_volume = _volume_percent(volume)
        # Windows Media Player COM object can handle mp3 playback.
        if _run_playback(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "$p = New-Object -ComObject WMPlayer.OCX.7;"
                    f"$p.URL = \"{path}\";"
                    f"$p.settings.volume = {wm_volume};"
                    "$p.controls.play();"
                    "while ($p.playState -ne 1) { Start-Sleep -Milliseconds 200 };"
                    "$p.close();"
                ),
            ],
            "wmplayer COM",
        ):
            return True

        return _run_playback(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(New-Object Media.SoundPlayer \"{path}\").PlaySync()",
            ],
            "powershell SoundPlayer",
        )

    if sys.platform == "darwin":
        afplay_cmd = ["afplay"]
        afplay_volume = _afplay_volume(volume)
        if afplay_volume is not None:
            afplay_cmd.extend(["-v", afplay_volume])
        afplay_cmd.append(path)
        return _run_playback(afplay_cmd, "afplay")

    # Linux/WSL fallbacks
    for candidate in (["aplay", path], ["paplay", path]):
        if shutil.which(candidate[0]):
            return _run_playback(candidate, candidate[0])

    return False


def _run_playback(cmd: list[str], label: str) -> bool:
    try:
        result = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,  # avoid hangs on broken players
        )
        if result.returncode == 0:
            return True
        logger.debug("%s returned code %s", label, result.returncode)
    except FileNotFoundError:
        logger.debug("%s not found on PATH", label)
    except subprocess.TimeoutExpired:
        logger.debug("%s timed out; skipping playback", label)
    except Exception as exc:  # pragma: no cover - best effort
        logger.debug("%s playback failed: %s", label, exc)
    return False


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except Exception as exc:  # pragma: no cover - non-critical cleanup
        logger.debug("Failed to remove temp audio file %s: %s", path, exc)


def _attempt_play_with_retries(
    path: str, attempts: int = 3, delay_seconds: float = 1.0, volume: float | None = None
) -> bool:
    """
    Retry auto playback a few times to tolerate slow startup of platform players.
    """
    for idx in range(attempts):
        if _auto_play_file(path, volume=volume):
            return True
        if idx < attempts - 1:
            time.sleep(delay_seconds)
    return False
