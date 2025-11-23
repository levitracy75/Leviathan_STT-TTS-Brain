"""
Speech-to-text utilities: push-to-talk recording and OpenAI Whisper transcription.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import uuid
from io import BytesIO
from typing import Optional
from urllib import error, request

logger = logging.getLogger(__name__)

try:
    from .listen import record_push_to_talk  # noqa: F401
except Exception as exc:  # pragma: no cover - optional dependency
    logger.debug("listen module unavailable: %s", exc)
    record_push_to_talk = None  # type: ignore

OPENAI_WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_WHISPER_MODEL = "whisper-1"
DEFAULT_LOCAL_WHISPER_MODEL = "base"


def transcribe_audio_bytes(
    audio_bytes: bytes,
    api_key: str,
    model: str | None = None,
    language: Optional[str] = None,
) -> str:
    """
    Send audio bytes to OpenAI Whisper API and return the text transcription.
    Uses urllib to avoid extra dependencies.
    """
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for transcription.")
    if not audio_bytes:
        return ""

    boundary = uuid.uuid4().hex
    body = _build_multipart_body(audio_bytes, boundary, model or DEFAULT_WHISPER_MODEL, language)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    }

    req = request.Request(OPENAI_WHISPER_URL, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=120) as resp:
            resp_data = resp.read()
            parsed = json.loads(resp_data.decode("utf-8"))
            return parsed.get("text", "")
    except error.HTTPError as err:
        body = ""
        try:
            body = err.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover
            body = "<unreadable error body>"
        raise RuntimeError(f"OpenAI transcription failed ({err.code}): {body}") from err
    except error.URLError as err:
        raise RuntimeError(f"OpenAI transcription failed: {err}") from err


def transcribe_auto(
    audio_bytes: bytes,
    api_key: Optional[str],
    openai_model: Optional[str] = None,
    language: Optional[str] = None,
    local_model: Optional[str] = DEFAULT_LOCAL_WHISPER_MODEL,
    prefer_local: bool = False,
) -> str:
    """
    Try OpenAI Whisper first (if api_key is provided), otherwise fall back to local whisper.
    """
    errors = []
    if api_key and not prefer_local:
        try:
            return transcribe_audio_bytes(audio_bytes, api_key=api_key, model=openai_model, language=language)
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"openai: {exc}")

    try:
        return transcribe_local_whisper(audio_bytes, model=local_model, language=language)
    except Exception as exc:  # pragma: no cover - optional dependency
        errors.append(f"local: {exc}")
        raise RuntimeError("; ".join(errors)) from exc


def transcribe_audio_file(
    path: str,
    api_key: str,
    model: str | None = None,
    language: Optional[str] = None,
) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Audio file not found: {path}")
    with open(path, "rb") as f:
        data = f.read()
    return transcribe_audio_bytes(data, api_key=api_key, model=model, language=language)


def transcribe_local_whisper(
    audio_bytes: bytes,
    model: Optional[str] = DEFAULT_LOCAL_WHISPER_MODEL,
    language: Optional[str] = None,
) -> str:
    """
    Local transcription using the openai/whisper package (CPU/GPU).
    Requires: pip install openai-whisper && ffmpeg on PATH.
    """
    try:
        import whisper  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError("Local Whisper requires 'pip install openai-whisper' and ffmpeg on PATH.") from exc

    try:
        import torch  # type: ignore
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        device = "cpu"

    chosen_model = model or DEFAULT_LOCAL_WHISPER_MODEL
    logger.info("Transcribing locally with Whisper model=%s device=%s", chosen_model, device)
    _ensure_ffmpeg_on_path()
    audio_path = _bytes_to_temp_wav(audio_bytes)
    try:
        wmodel = whisper.load_model(chosen_model, device=device)
        result = wmodel.transcribe(audio_path, language=language)
        return result.get("text", "")
    finally:
        try:
            os.remove(audio_path)
        except Exception:
            pass


def _build_multipart_body(audio_bytes: bytes, boundary: str, model: str, language: Optional[str]) -> bytes:
    """
    Build a multipart/form-data payload for Whisper transcription.
    """
    buffer = BytesIO()
    sep = f"--{boundary}\r\n".encode("utf-8")

    # file part
    buffer.write(sep)
    buffer.write(
        b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
    )
    buffer.write(b"Content-Type: audio/wav\r\n\r\n")
    buffer.write(audio_bytes)
    buffer.write(b"\r\n")

    # model part
    buffer.write(sep)
    buffer.write(b'Content-Disposition: form-data; name="model"\r\n\r\n')
    buffer.write(model.encode("utf-8"))
    buffer.write(b"\r\n")

    if language:
        buffer.write(sep)
        buffer.write(b'Content-Disposition: form-data; name="language"\r\n\r\n')
        buffer.write(language.encode("utf-8"))
        buffer.write(b"\r\n")

    buffer.write(f"--{boundary}--\r\n".encode("utf-8"))
    return buffer.getvalue()


def _bytes_to_temp_wav(data: bytes) -> str:
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".wav")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def _ensure_ffmpeg_on_path() -> None:
    """
    Ensure ffmpeg is discoverable. If not, try to locate a common Windows install and prepend to PATH.
    """
    if shutil.which("ffmpeg"):
        return

    candidates = []
    for root in (
        r"C:\ffmpeg",
        os.getenv("ProgramFiles"),
        os.getenv("ProgramFiles(x86)"),
    ):
        if not root:
            continue
        candidates.extend(glob.glob(os.path.join(root, "**", "ffmpeg.exe"), recursive=True))

    if not candidates:
        raise RuntimeError("ffmpeg not found on PATH. Install ffmpeg and ensure ffmpeg.exe is reachable.")

    ffmpeg_path = candidates[0]
    ffmpeg_dir = os.path.dirname(ffmpeg_path)
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    logger.info("Added ffmpeg to PATH from %s", ffmpeg_dir)
