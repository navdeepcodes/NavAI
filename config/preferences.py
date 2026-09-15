"""User preferences, stored beside Mike's other local state.

Small on purpose: the engines already hold their own behaviour, this only
records the choices a person has made about them. Everything stays on disk in
one JSON file next to the memory database.
"""
from __future__ import annotations

import json
import threading
from typing import Any

from hostplatform.storage import data_dir, preferences_path
from logs.logger import logger

_DIR = data_dir()
_PATH = preferences_path()

DEFAULTS: dict[str, Any] = {
    "voice_enabled": True,
    "voice_name": "Samantha",
    "voice_rate": 185,
    "wake_word_enabled": True,
    "edge_enabled": True,
    "reduced_motion": False,
}

_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _cache

    if _cache is not None:
        return _cache

    values = dict(DEFAULTS)
    try:
        if _PATH.exists():
            stored = json.loads(_PATH.read_text())
            if isinstance(stored, dict):
                # Only accept keys we know about, so a stale file can't
                # smuggle in surprises.
                values.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except Exception:
        logger.exception("Could not read preferences; using defaults.")

    _cache = values
    return _cache


def get(key: str, default: Any = None) -> Any:
    with _lock:
        return _load().get(key, DEFAULTS.get(key, default))


def all_values() -> dict[str, Any]:
    with _lock:
        return dict(_load())


def set_value(key: str, value: Any) -> None:
    if key not in DEFAULTS:
        return

    with _lock:
        values = _load()
        values[key] = value
        try:
            _DIR.mkdir(parents=True, exist_ok=True)
            _PATH.write_text(json.dumps(values, indent=2))
        except Exception:
            logger.exception("Could not save preferences.")


def path() -> str:
    return str(_PATH)
