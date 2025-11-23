"""
Lightweight .env loader to keep secrets local.
Prefer this over adding a dependency during early scaffolding.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def load_env(dotenv_path: str | Path = ".env") -> None:
    """
    Parse a .env file and merge values into os.environ if not already set.
    Lines starting with '#' or blank lines are ignored.
    """
    path = Path(dotenv_path)
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """
    Fetch an environment variable with optional default/required semantics.
    """
    value = os.environ.get(key, default)
    if required and value is None:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value
