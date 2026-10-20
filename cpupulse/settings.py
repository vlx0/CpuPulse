"""Remember UI prefs."""

from __future__ import annotations

import json
from pathlib import Path

_DIR = Path.home() / ".cpupulse"
_FILE = _DIR / "settings.json"

INTERVALS = (
    (0.5, "0,5 с"),
    (1.0, "1 с"),
    (2.0, "2 с"),
    (5.0, "5 с"),
    (10.0, "10 с"),
)
DEFAULT_INTERVAL = 1.0


def _load() -> dict:
    try:
        raw = json.loads(_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    cur = _load()
    cur.update(data)
    _FILE.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")


def load_interval() -> float:
    val = _load().get("proc_sec", DEFAULT_INTERVAL)
    try:
        sec = float(val)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL
    allowed = {s for s, _ in INTERVALS}
    return sec if sec in allowed else DEFAULT_INTERVAL


def save_interval(sec: float) -> None:
    _save({"proc_sec": sec})


def load_show_cores() -> bool:
    return bool(_load().get("show_cores", False))


def save_show_cores(on: bool) -> None:
    _save({"show_cores": bool(on)})
