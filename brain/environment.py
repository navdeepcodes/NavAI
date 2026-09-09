from __future__ import annotations

import time
from datetime import datetime


_CACHE_TTL_SECONDS = 15.0

_cached_app: str | None = None
_cached_at: float = 0.0


def _frontmost_app() -> str | None:
    """Which application the user is actually looking at, for ambient context.

    Used to shell out to `osascript` and ask System Events directly — a
    second, independent implementation of a question computer/ already
    answers, and a worse one: asking System Events for the frontmost
    process is Automation-gated in TCC and prompts for a permission this
    purely-informational feature has no need to ask for, where
    computer.macos's CGWindowList-based answer needs none. Reusing it also
    means this line of context gains Windows support the moment
    computer/windows.py implements frontmost_app(), instead of needing a
    second platform branch of its own.
    """

    global _cached_app, _cached_at

    now = time.monotonic()

    if now - _cached_at < _CACHE_TTL_SECONDS:
        return _cached_app

    try:
        from computer.base import get_controller

        _cached_app = get_controller().frontmost_app()

    except Exception:
        # No adapter for this OS yet, or the query itself failed -- either
        # way this is ambient flavour text, not something worth surfacing
        # as an error.
        _cached_app = None

    _cached_at = now

    return _cached_app


def _time_of_day() -> str:

    hour = datetime.now().hour

    if hour < 5:
        return "late night"
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    if hour < 21:
        return "evening"

    return "night"


def describe_environment() -> str:

    try:

        day = datetime.now().strftime("%A")
        period = _time_of_day()
        app = _frontmost_app()

        line = f"It's {day} {period}."

        if app:
            line += f" The user currently has {app} focused."

        parts = [line]

        # When an editor is attached it describes itself here, which is how the
        # brain learns about the IDE without any editor-specific code of its own.
        editor = _describe_editor()
        if editor:
            parts.append(editor)

        return "\n\n".join(parts)

    except Exception:

        return ""


def _describe_editor() -> str:
    """
    Never raises and never blocks — reads the last snapshot the editor pushed,
    and returns "" when nothing is connected.
    """

    try:
        from ide import manager

        return manager.describe()

    except Exception:
        return ""
