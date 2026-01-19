from __future__ import annotations

import argparse
import logging
import threading
import time
import ctypes
import tkinter as tk

from commands import handle_command, parse_intent
from config import configure_logging, load_settings
from leviathan_brain import leviathan_reply
from overlay import clear_state, write_context, write_state, read_gamestate, read_gamestate_log
from overlay.server import start_overlay_server
from stt import record_push_to_talk, transcribe_auto
from tts import speak, stream_speech
import keyboard  # type: ignore

logger = logging.getLogger("cli")
SPEECH_LOCK = threading.Lock()


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
        "--use-context",
        action="store_true",
        help="Include latest browser context (url/selection) if available.",
    )
    parser.add_argument(
        "--capture-clipboard-hotkey",
        default="ctrl+shift+c",
        help="Hotkey to capture clipboard + window title into context (default: ctrl+shift+c).",
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

    if args.use_context:
        _start_clipboard_listener(args)
    _start_gamestate_watcher(args)

    if args.say:
        ctx = _maybe_context(args)
        line = leviathan_reply(args.say, context=ctx)
        logger.info("Leviathan will say: %s", line)
        _speak_with_overlay(line, args, stream=args.stream)
        return

    # Default to push-to-talk loop
    run_listen_mode(args, settings)


def _speak_line(line: str, stream: bool = False) -> None:
    try:
        logger.info("Speaking line (stream=%s): %s", stream, line)
        if stream:
            stream_speech(line)
        else:
            speak(line)
    except Exception as exc:
        logger.error("TTS failed: %s", exc)
        raise


def _speak_with_overlay(line: str, args, stream: bool = False) -> None:
    with SPEECH_LOCK:
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
            ctx = _maybe_context(args)
            line = leviathan_reply(transcript, context=ctx)
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


def _maybe_context(args) -> str | None:
    if not args.use_context:
        return args.context
    try:
        from overlay import read_context

        ctx = read_context("overlay/context.json")
        bits = []
        if ctx.get("url"):
            bits.append(f"URL: {ctx['url']}")
        if ctx.get("selection"):
            bits.append(f"Selection: {ctx['selection']}")
        if bits:
            return " | ".join(bits)
    except Exception:
        return args.context
    return args.context


def _start_clipboard_listener(args) -> None:
    hotkey = args.capture_clipboard_hotkey
    try:
        keyboard.add_hotkey(hotkey, lambda: _capture_clipboard_to_context())
        logger.info("Clipboard capture hotkey active: %s", hotkey)
    except Exception as exc:
        logger.error("Failed to register clipboard hotkey: %s", exc)


def _capture_clipboard_to_context() -> None:
    selection = _read_clipboard_text()
    title = _get_active_window_title()
    try:
        write_context("overlay/context.json", url=title, selection=selection)
        logger.info("Captured context from clipboard (title=%s, chars=%s)", title, len(selection))
    except Exception as exc:
        logger.error("Failed to write clipboard context: %s", exc)


def _read_clipboard_text() -> str:
    try:
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return text or ""
    except Exception:
        return ""


def _get_active_window_title() -> str:
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    except Exception:
        return ""


def _start_gamestate_watcher(args) -> None:
    thread = threading.Thread(target=_gamestate_loop, args=(args,), daemon=True)
    thread.start()
    logger.info("Gamestate watcher started (overlay/gamestate.json)")


def _gamestate_loop(args) -> None:
    # Seed announced set from existing log to avoid replaying old events.
    announced_ids = set()
    try:
        for evt in read_gamestate_log("overlay/gamestate.log"):
            evt_id = evt.get("event_id") or evt.get("event")
            if evt_id:
                announced_ids.add(evt_id)
    except Exception:
        pass
    while True:
        try:
            new_events = []
            for evt in read_gamestate_log("overlay/gamestate.log"):
                evt_id = evt.get("event_id") or evt.get("event")
                if evt_id and evt_id not in announced_ids:
                    announced_ids.add(evt_id)
                    new_events.append(evt)

            if new_events:
                # Preserve arrival order; if multiple, announce in the order they were logged.
                new_events = list(new_events)
                winner_event = next((e for e in new_events if e.get("winner")), None)
                if winner_event:
                    w = winner_event.get("winner", {}) or {}
                    wname = w.get("name") or winner_event.get("event", "Unknown victor")
                    reason = w.get("reason") or ""
                    announcement = leviathan_reply(
                        f"Declare victory: {wname} wins. Reason: {reason}. Include the winner name verbatim and clearly."
                    )
                else:
                    if len(new_events) == 1:
                        event = new_events[0].get("event")
                        announcement = leviathan_reply(
                            f"Announce clearly the elimination: {event}. Include the team name verbatim."
                        )
                    else:
                        names = [e.get("event", "") for e in new_events if e.get("event")]
                        joined = "; ".join(names)
                        announcement = leviathan_reply(
                            f"Announce clearly these eliminations together: {joined}. Include each team name verbatim."
                        )
                logger.info("Announcing game events batch: %s", [e.get('event') for e in new_events])
                try:
                    _speak_with_overlay(announcement, args, stream=args.stream)
                    _clear_overlay(args)
                except Exception as exc:
                    logger.error("Failed to speak game event batch: %s", exc)
        except Exception as exc:
            logger.debug("Gamestate watcher error: %s", exc)
        time.sleep(1.0)


if __name__ == "__main__":
    main()
