"""
Intent parsing and routing stubs.
Phase 4 will implement real parsing and handlers.
"""
from __future__ import annotations

import enum
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Intent(enum.Enum):
    UNKNOWN = "unknown"
    REVIEW_CODE = "review_code"
    GENERATE_EVENT = "generate_event"
    EXPLAIN_LOGIC = "explain_logic"


def parse_intent(command_text: str) -> Intent:
    """
    Very naive parser to be replaced in Phase 4.
    """
    text = command_text.lower()
    if "review" in text:
        return Intent.REVIEW_CODE
    if "event" in text:
        return Intent.GENERATE_EVENT
    if "explain" in text or "logic" in text:
        return Intent.EXPLAIN_LOGIC
    return Intent.UNKNOWN


def handle_command(intent: Intent, args: Optional[Dict[str, Any]] = None) -> str:
    """
    Placeholder command handler. Returns a string summary.
    """
    logger.info("Handling intent=%s args=%s", intent, args)
    return f"Handled {intent.value} with args={args or {}}"
