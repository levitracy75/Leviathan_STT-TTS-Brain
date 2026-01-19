from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


def write_context(path: str | Path, url: str | None = None, selection: str | None = None) -> Path:
    payload: Dict[str, Any] = {
        "url": url or "",
        "selection": selection or "",
        "ts": time.time(),
    }
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return out_path


def read_context(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"url": "", "selection": "", "ts": 0}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "url": data.get("url", "") or "",
                "selection": data.get("selection", "") or "",
                "ts": data.get("ts", 0) or 0,
            }
    except Exception:
        pass
    return {"url": "", "selection": "", "ts": 0}
