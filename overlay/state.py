from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Literal, Optional

OverlayMode = Literal["speak", "think", "clear"]


def write_state(
    path: str | Path,
    mode: OverlayMode,
    text: str = "",
    font_size: int = 30,
) -> Path:
    """
    Write overlay state to a JSON file for the browser overlay.
    """
    payload = {
        "mode": mode,
        "text": text,
        "font_size": font_size,
        "ts": time.time(),
    }
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return out_path


def clear_state(path: str | Path) -> Path:
    return write_state(path, mode="clear", text="")
