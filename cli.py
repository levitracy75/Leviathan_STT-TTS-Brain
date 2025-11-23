from __future__ import annotations

import argparse
import logging
import threading
import time

from commands import handle_command, parse_intent
from config import configure_logging, load_settings
from leviathan_brain import leviathan_reply
from overlay import clear_state, write_state
from overlay.server import start_overlay_server
from stt import record_push_to_talk, transcribe_auto
from tts import speak, stream_speech

logger = logging.getLogger("cli")


def main() -> None:
    parser = argparse.ArgumentParser(description="Leviathan control CLI")
    parser.add_argument("--say", help="Feed text to Leviathan for speech.")
    parser.add_argument(
        "--context",
        help="Optional context string for the Leviathan brain reply.",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use streaming TTS playback.",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="(Default) Use local Whisper only; OpenAI STT API is skipped.",
    )
    parser.add_argument(
        "--overlay-path",
        default="overlay/state.json",
        help="Overlay state path (JSON). Defaults to overlay/state.json.",
    )
    parser.add_argument(
        "--overlay-mode",
        choices=["speak", "think"],
        default="speak",
        help="Overlay style: speak bubble or thinking bubbles.",
    )
    parser.add_argument(
        "--overlay-font-size",
        type=int,
        default=30,
        help="Font size for overlay text.",
    )
    parser.add_argument(
        "--overlay-host",
        default="127.0.0.1",
        help="Host for overlay server.",
    )
    parser.add_argument(
        "--overlay-port",
        type=int,
        default=5005,
        help="Port for overlay server.",
    )
    parser.add_argument(
        "--log-level",
        help="Override log level (e.g., DEBUG, INFO).",
    )
    args = parser.parse_args()

    configure_logging(args.log_level)
    settings = load_settings()
    logger.debug(
        "Loaded settings: project_root=%s openai_key=%s elevenlabs_key=%s",
        settings.project_root,
        bool(settings.openai_api_key),
        bool(settings.elevenlabs_api_key),
    )

    # Start overlay server if using JSON state
    if str(args.overlay_path).lower().endswith(".json"):
        start_overlay_server(args.overlay_path, host=args.overlay_host, port=args.overlay_port)
        clear_state(args.overlay_path)

    if args.say:
        line = leviathan_reply(args.say, context=args.context)
        logger.info("Leviathan will say: %s", line)
        _speak_with_overlay(line, args, stream=args.stream)
        return

    # Default to push-to-talk loop
    run_listen_mode(args, settings)


def _speak_line(line: str, stream: bool = False) -> None:
    if stream:
        stream_speech(line)
    else:
        speak(line)


def _speak_with_overlay(line: str, args, stream: bool = False) -> None:
    _maybe_render_overlay(line, args, mode="speak")
    # Play audio synchronously so we can clear after playback finishes.
    _speak_line(line, stream=stream)
    _clear_overlay(args)


def run_listen_mode(args, settings) -> None:
    if not record_push_to_talk:
        logger.error(
            "Push-to-talk requires sounddevice, keyboard, numpy. Install with: pip install sounddevice keyboard numpy"
        )
        return

    logger.info("Push-to-talk mode. Hold Ctrl to record, release to transcribe. Ctrl+C to exit.")
    stt_model = settings.openai_stt_model or "whisper-1"
    local_model = settings.local_whisper_model or "base"

    try:
        while True:
            audio = record_push_to_talk()
            if not audio:
                continue
            _render_thinking(args)
            try:
                transcript = transcribe_auto(
                    audio,
                    api_key=settings.openai_api_key,
                    openai_model=stt_model,
                    local_model=local_model,
                    prefer_local=True,  # always prefer local STT
                )
            except Exception as exc:
                logger.error("Transcription failed: %s", exc)
                _clear_overlay(args)
                continue

            transcript = transcript.strip()
            if not transcript:
                logger.info("Heard nothing recognizable.")
                _clear_overlay(args)
                continue

            logger.info("You said: %s", transcript)
            line = leviathan_reply(transcript, context=args.context)
            logger.info("Leviathan will say: %s", line)
            _speak_with_overlay(line, args, stream=args.stream)
    except KeyboardInterrupt:
        logger.info("Exiting listen mode.")

def _maybe_render_overlay(text: str, args, mode: str | None = None) -> None:
    if not getattr(args, "overlay_path", None):
        return
    try:
        if str(args.overlay_path).lower().endswith(".json"):
            write_state(
                args.overlay_path,
                mode=mode or args.overlay_mode,
                text=text,
                font_size=args.overlay_font_size,
            )
    except Exception as exc:
        logger.error("Failed to render overlay: %s", exc)


def _render_thinking(args) -> None:
    if not getattr(args, "overlay_path", None):
        return
    try:
        if str(args.overlay_path).lower().endswith(".json"):
            write_state(args.overlay_path, mode="think", text="...", font_size=args.overlay_font_size)
    except Exception as exc:
        logger.error("Failed to render thinking overlay: %s", exc)


def _clear_overlay(args, delay: float = 1.0) -> None:
    if not getattr(args, "overlay_path", None):
        return
    if delay > 0:
        time.sleep(delay)
    try:
        if str(args.overlay_path).lower().endswith(".json"):
            clear_state(args.overlay_path)
    except Exception as exc:
        logger.error("Failed to clear overlay: %s", exc)


if __name__ == "__main__":
    main()
