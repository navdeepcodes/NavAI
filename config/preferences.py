"""User preferences, stored beside Mike's other local state.

Small on purpose: the engines already hold their own behaviour, this only
records the choices a person has made about them. Everything stays on disk in
one JSON file next to the memory database.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from logs.logger import logger

# MIKE_DATA_DIR overrides the real per-user data directory — set by
# tests/_isolate.py (or a pytest fixture) so tests can never touch the
# real preferences file. Unset in normal app runs.
_DIR = Path(os.environ["MIKE_DATA_DIR"]) if os.environ.get("MIKE_DATA_DIR") \
    else Path.home() / "Library" / "Application Support" / "Mike"
_PATH = _DIR / "preferences.json"

DEFAULTS: dict[str, Any] = {
    "voice_enabled": True,
    "voice_name": "Samantha",
    "voice_rate": 185,

    # Which voice Mike speaks in. "native" is the macOS `say` voice above and
    # is always available; "qwen" is the local neural voice, which is only
    # used if its model and runtime are present and falls back here if not.
    #
    # These have to be declared to exist. set_value() silently drops anything
    # not listed in this dict — deliberately, so a stale file cannot smuggle
    # in settings — which meant the voice choice could be read but never
    # saved, and every attempt to configure it looked like it had worked.
    "voice_provider": "native",
    "voice_qwen_speaker": "Ryan",

    # How Mike should sound, in plain English, handed to the model as its
    # `instruct` input. Chosen by listening: positive situational framing
    # ("picking up a conversation") produced natural delivery where adjectives
    # and negations ("do not perform") produced a slow, over-articulated
    # reading of every word. Keep it short — instructions past roughly 60
    # characters destabilised generation and truncated sentences mid-word.
    "voice_qwen_instruct": "Picking up a conversation. Calm, grounded, matter-of-fact.",
    "wake_word_enabled": True,
    "edge_enabled": True,
    "reduced_motion": False,
    "onboarding_complete": False,
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
