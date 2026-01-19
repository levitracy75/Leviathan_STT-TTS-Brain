# Leviathan STT-TTS Brain

Leviathan is a streamer co-host pipeline that listens to push-to-talk audio, transcribes it, generates a short reply from a chosen LLM backend, speaks it via ElevenLabs, and drives a browser overlay with speech or thinking bubbles. It can also watch for game-state events and announce eliminations or winners.

## Purpose

Provide a local-first, real-time voice loop for livestreams: quick human input, fast AI response, audible output, and an on-screen overlay that keeps the audience in the loop.

## Scope

In scope:
- Single-operator, local execution (desktop CLI + local overlay server).
- Push-to-talk STT, LLM response, and ElevenLabs TTS playback.
- Browser overlay (OBS/Streamlabs friendly) driven by JSON state.
- Optional clipboard context capture and gamestate announcements.

Out of scope (current state):
- Multi-user sessions, remote control, or persistent conversation memory.
- Fully featured intent routing (commands are stubs).
- Turn-by-turn chat UI beyond the overlay bubble.

## Project Structure

- `cli.py` - Orchestrates STT -> LLM -> TTS, overlay updates, and gamestate watch loop.
- `leviathan_brain/` - LLM backend selection (Ollama, OpenAI, or persona fallback).
- `stt/` - Push-to-talk recording and transcription (OpenAI Whisper or local whisper).
- `tts/` - ElevenLabs client + audio playback helpers.
- `overlay/` - Overlay state, browser server, static UI, and gamestate/context stores.
- `config/` - Logging and .env-based settings.

## How It Works

1) CLI starts the overlay server and watchers.
2) Push-to-talk capture records audio into WAV bytes.
3) STT runs locally (or OpenAI Whisper if wired in) to obtain a transcript.
4) Leviathan Brain selects an LLM backend (Ollama, OpenAI, or persona fallback).
5) ElevenLabs synthesizes speech; ffplay streams audio when available.
6) Overlay state is updated so the browser overlay animates the response.

## Quick Start

### 1) Install dependencies

Required for the CLI:
```bash
pip install keyboard
```

Recommended for push-to-talk recording:
```bash
pip install sounddevice numpy
```

Optional (only if you use these features):
```bash
pip install openai-whisper pillow
```

System tools:
- `ffmpeg` and `ffplay` on PATH for audio playback and local Whisper.

### 2) Configure `.env`

Create a `.env` file in the repo root:
```dotenv
ELEVENLABS_API_KEY=your_key
ELEVENLABS_VOICE_ID=your_voice_id
OPENAI_API_KEY=your_openai_key
LLM_PROVIDER=ollama   # or "openai" or "local"
OLLAMA_MODEL=llama3:8b
OPENAI_LLM_MODEL=gpt-4o-mini
LOCAL_WHISPER_MODEL=base
TTS_PLAYBACK_VOLUME=0.6
LOG_LEVEL=INFO
```

### 3) Run

Start the full pipeline:
```bash
python cli.py
```

Speak a direct line:
```bash
python cli.py --say "Leviathan, announce the victory."
```

Enable streaming TTS:
```bash
python cli.py --stream
```

Open the overlay in a browser or OBS:
```
http://127.0.0.1:5005
```

## CLI Flags (Key Options)

- `--say`: Feed text to Leviathan for speech.
- `--stream`: Stream TTS playback.
- `--use-context`: Include latest browser/clipboard context if available.
- `--capture-clipboard-hotkey`: Hotkey to capture clipboard + window title.
- `--overlay-path`: Path to overlay JSON state (default `overlay/state.json`).
- `--overlay-mode`: `speak` or `think`.
- `--overlay-font-size`: Bubble text size.
- `--overlay-host`, `--overlay-port`: Overlay server bind address.

## Gamestate Announcements

The overlay server accepts POSTs at `/gamestate` and appends to `overlay/gamestate.log`. The CLI watches that log and announces new events. It looks for:
- `event` or `event_id` for de-duplication and announcements.
- Optional `winner` object with `name` and `reason` for victory calls.

## Notes and Limitations

- The CLI imports `keyboard` at startup; install it even if you do not use hotkeys.
- Active window title capture uses Windows APIs via `ctypes`.
- Without `ffplay`, audio is written to a temp file and must be played manually.
- Command routing in `commands/` is placeholder logic.

