"""
Basic logging configuration for Leviathan.
"""
from __future__ import annotations

import logging
import os


DEFAULT_LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def configure_logging(level: str | None = None) -> None:
    """
    Configure root logging once with a consistent format.
    """
    log_level = (level or os.getenv("LOG_LEVEL") or DEFAULT_LOG_LEVEL).upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=LOG_FORMAT,
    )
