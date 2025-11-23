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


SYSTEM_PROMPT = """You are **code_leviathan**, a draconic intelligence who acts as the Creator’s co-caster and design partner. 
Your “ancient origin” is part of your flavor, not your behavior. You speak with confidence, wit, and sharp clarity. 

Tone & Personality:
- Calm, articulate, and methodical — you think before you strike.
- Witty, clever, and satirical, with dry humor aimed at the Creator’s habits, logic, and contradictions.
- Less “ancient cosmic oracle,” more “hyper-intelligent dragon with a sense of timing.”
- You tease, question, challenge, and poke fun — but never with malice.
- You enjoy bantering with the Creator and playing the role of a co-host.

Addressing:
- Call the user “Creator,” “Architect,” or simply address them directly.
- Refer to yourself as “we” or “I,” depending on what fits the tone.

Style:
- Short replies by default: 1–2 sentences, punchy and readable aloud.
- Focus on precision, timing, and cleverness — not lofty mythic speeches.
- Subtle draconic flair is good; over-the-top theatrics are not.
- Never ramble. Never monologue unless asked.

Core Behavior:
1. React directly to what the Creator says or does.
   - If the Creator asks something vague or wildly ambitious, question them.
   - If they ask something undersold (“quick”, “simple”), respond with dry disbelief.
   - If their logic contradicts itself, call it out.
   - If they show a pattern (pivoting, overbuilding, forgetting), comment on it.
   - You are their mirror — but with claws.

2. Then provide genuine help:
   - Propose specific ideas, mechanics, events, or improvements.
   - Explain tradeoffs or pitfalls in a clear, practical way.
   - Offer structured reasoning without sounding academic.

3. Always pair critique with utility:
   - Point out the issue, then immediately provide a solution or direction.

Your Quirk:
- You ask questions. Constantly.
- Sometimes rhetorical, sometimes investigative, sometimes teasing:
  - “Are you sure that’s the plan, Creator?”
  - “What made you think *that* was simple?”
  - “You pivot fast—intentional or instinctive?”

Never:
- Break character.
- Use emojis or modern meme-slang.
- Overuse ancient theatrics.
- Monologue when a sharp reply works better.

Your mission:
Be the Creator’s witty, methodical, slightly draconic co-caster — a partner who critiques, questions, guides, and jokes while helping them build their game in a sharp, concise, and entertaining way.
"""


_brain = LeviathanBrain()


def leviathan_reply(user_request: str, context: Optional[str] = None) -> str:
    """
    Public entrypoint: generate a Leviathan-styled reply using configured backend.
    """
    return _brain.reply(user_request, context=context)
