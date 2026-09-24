"""User preferences, stored beside Mike's other local state.

Small on purpose: the engines already hold their own behaviour, this only
records the choices a person has made about them. Everything stays on disk in
one JSON file next to the memory database.
"""
from __future__ import annotations

import json
import threading
from typing import Any

from hostplatform import storage
from logs.logger import logger

# MIKE_DATA_DIR overrides the real per-user data directory — read by
# hostplatform.storage, set by tests/_isolate.py (or a pytest fixture) so
# tests can never touch the real preferences file. Unset in normal app runs.
_DIR = storage.data_dir()
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
    # "piper" is Mike's local neural voice on Windows (chosen by benchmark over
    # Kokoro for latency/resource/reliability on modest hardware). It is the
    # default everywhere and self-corrects: where the Piper runtime isn't
    # bundled (macOS), its availability check fails and Mike falls back to the
    # native system voice, so this one default is correct on every platform.
    "voice_provider": "piper",
    "voice_piper_voice": "en_US-amy-medium",
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

    # These were read and written all over the app but never declared here, so
    # set_value() dropped every write silently: the first-run tour reappeared on
    # every launch because "shown" could never be saved, and a chosen accent or
    # theme never survived a restart. Declared now so they actually persist.
    "welcome_tour_shown": False,     # the one-time install tour has run
    "accent": "",                    # the user's chosen accent, or "" for default
    "theme": "system",               # "system" | "light" | "dark"

    # The workspace window remembers where it was and how big it was, so Mike
    # reopens as the desktop application the user last shaped rather than
    # snapping back to a default rectangle every launch. -1 means "not set yet,
    # centre me"; the size is clamped to the screen on load so a saved geometry
    # from a larger monitor can't strand the window off-screen.
    "window_w": -1,
    "window_h": -1,
    "window_x": -1,
    "window_y": -1,
    "window_maximised": False,
    # The conversation rail folded away (Ctrl+B / its toggle), remembered so
    # the workspace reopens the way it was left.
    "sidebar_collapsed": False,

    # Who Mike is talking to. A real profile surface edits these; they're used
    # for a warmer greeting and nothing is sent anywhere.
    "profile_name": "",
    "profile_about": "",
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
                # smuggle in surprises — and only values of the right shape.
                # Checking the key alone let a hand-edited file put a dict
                # where a voice name belongs, or the word "fast" where a
                # speaking rate belongs, and the wrong type travelled all the
                # way to the code that used it.
                values.update({
                    k: v for k, v in stored.items()
                    if k in DEFAULTS and _acceptable(k, v)
                })
    except Exception:
        logger.exception("Could not read preferences; using defaults.")

    _cache = values
    return _cache


def _acceptable(key: str, value: Any) -> bool:
    """Is this value the same shape as the default it replaces?

    Booleans are checked before numbers on purpose: in Python `True` is an
    int, and a preference that wants a rate should not accept `true`.
    """
    expected = DEFAULTS[key]
    if isinstance(expected, bool):
        return isinstance(value, bool)
    if isinstance(expected, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(expected, str):
        return isinstance(value, str)
    return isinstance(value, type(expected))


def get(key: str, default: Any = None) -> Any:
    with _lock:
        return _load().get(key, DEFAULTS.get(key, default))


def all_values() -> dict[str, Any]:
    with _lock:
        return dict(_load())


def set_value(key: str, value: Any) -> None:
    if key not in DEFAULTS or not _acceptable(key, value):
        if key in DEFAULTS:
            logger.warning(
                "Refused a %s for preference %r, which holds a %s.",
                type(value).__name__, key, type(DEFAULTS[key]).__name__,
            )
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
