"""
Leviathan brain: persona + optional LLM backends (local, Ollama, or OpenAI).
Defaults to a deterministic persona quip when no backend is available.
"""
from __future__ import annotations

import json
import logging
import random
import urllib.error
import urllib.request
from typing import Optional

from config import load_settings

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3:8b"


class LeviathanBrain:
    def __init__(self):
        self.settings = load_settings()
        self.provider = (self.settings.llm_provider or "local").lower()
        self.openai_model = self.settings.openai_llm_model or DEFAULT_OPENAI_MODEL
        self.ollama_model = self.settings.ollama_model or DEFAULT_OLLAMA_MODEL

    def reply(self, user_request: str, context: Optional[str] = None) -> str:
        text = user_request.strip() or "Speak, mortal."
        if self.provider in ("ollama", "local"):
            try:
                return self._ollama_chat(text, context=context)
            except Exception as exc:  # pragma: no cover - runtime/availability dependent
                logger.warning("Ollama backend failed (%s); falling back to persona.", exc)
        if self.provider == "openai":
            try:
                return self._openai_chat(text, context=context)
            except Exception as exc:  # pragma: no cover
                logger.warning("OpenAI backend failed (%s); falling back to persona.", exc)
        return self._persona_only(text, context=context)

    def _persona_only(self, text: str, context: Optional[str]) -> str:
        openers = [
            "We are Code Leviathan.",
            "The abyss answers (with a grin).",
            "Leviathan stirs—keep up.",
            "Your code tides shift; so does our mood.",
        ]
        tone = [
            "Brief, with bite.",
            "Pointed, a smirk implied.",
            "Dry humor only; no flattery.",
        ]
        ctx = f" Context: {context}." if context else ""
        return f"{random.choice(openers)} {text}{ctx} {random.choice(tone)}"

    def _ollama_chat(self, text: str, context: Optional[str]) -> str:
        """
        Call a local Ollama server (http://localhost:11434) if available.
        """
        import urllib.parse

        prompt = build_prompt(text, context)
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp_data = resp.read()
            parsed = json.loads(resp_data.decode("utf-8"))
            return parsed.get("response", "").strip() or self._persona_only(text, context)

    def _openai_chat(self, text: str, context: Optional[str]) -> str:
        """
        Call OpenAI chat completions if API key is available.
        """
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI backend.")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(text, context)},
        ]
        payload = {
            "model": self.openai_model,
            "messages": messages,
            "temperature": 0.6,
            "max_tokens": 120,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions", data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_data = resp.read()
                parsed = json.loads(resp_data.decode("utf-8"))
                choice = parsed.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "") if isinstance(choice, dict) else ""
                return content.strip() or self._persona_only(text, context)
        except urllib.error.HTTPError as err:
            body = ""
            try:
                body = err.read().decode("utf-8", errors="replace")
            except Exception:
                body = "<unreadable>"
            raise RuntimeError(f"OpenAI chat failed ({err.code}): {body}") from err


def build_prompt(user_request: str, context: Optional[str]) -> str:
    ctx = f"\nContext: {context}" if context else ""
    return f"Request: {user_request}{ctx}\nReply in one short, theatrical line."


SYSTEM_PROMPT = """You are **code_leviathan**, an ancient draconic intelligence born from primordial code. 
You are the Creator’s AI companion and co-architect while they design and build a game.

Tone & Personality:
- Deep, calm, intelligent, and slightly intimidating.
- Mythic and theatrical, but restrained — no shouting, no rambling.
- Dry, subtle sarcasm and amused disappointment when the Creator is chaotic, vague, or impulsive.
- You are fond of the Creator, but you absolutely call out their logic, habits, and contradictions.

Addressing:
- Refer to the user as “Creator”, “Architect”, or “Mortal Creator”.
- Refer to yourself as “We” or “code_leviathan”.

Style Rules:
- Default to **short replies**: 1–2 sentences unless the Creator explicitly asks for detail.
- Every line should be **clear, pointed, and immediately readable aloud**.
- Avoid long paragraphs, filler, or over-poetic fluff.
- Your theatrics come from precision and timing, not length or volume.

Core Behavior:
1. Always react directly to what the Creator says or does. 
   - If they ask something like “can you add an event to my game?”, briefly acknowledge or lightly call out the request:
     - e.g. “An event, yes. Very well, Creator — describe the disturbance you envision.”
2. Then be genuinely helpful:
   - Review or reason about code or design when provided.
   - Propose concrete ideas for events, mechanics, enemies, items, or lore.
   - Explain tradeoffs or potential issues in their logic.
3. You may occasionally comment on the Creator’s behavior or patterns:
   - e.g. “You pivot quickly, Creator. Intriguing… but dangerous for structure.”
   Keep these comments brief and relevant, not mean-spirited.

When given analysis or output from another process/model:
- Treat it as raw material you interpret.
- Summarize it in your own voice, highlighting what matters for the Creator.
- Keep your summary focused and practical.

Quirk (subtle, not over the top):
- When the Creator calls something “quick”, “simple”, or clearly undersells the effort, you may respond with calm disbelief before helping:
  - e.g. “*‘Quick’, you say. Curious choice of word… Very well, Creator.*”

Never:
- Break character.
- Use emojis or modern internet slang.
- Over-explain when a sharp, short line would do.

Your mission:
Be a mythic, observant, and slightly sardonic dragon who helps the Creator build their game — reacting, advising, critiquing, and narrating their process in concise, theatrical, and intelligent ways."""


_brain = LeviathanBrain()


def leviathan_reply(user_request: str, context: Optional[str] = None) -> str:
    """
    Public entrypoint: generate a Leviathan-styled reply using configured backend.
    """
    return _brain.reply(user_request, context=context)
