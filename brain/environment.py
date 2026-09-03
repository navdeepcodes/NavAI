from __future__ import annotations

import subprocess
import time
from datetime import datetime


_CACHE_TTL_SECONDS = 15.0

_cached_app: str | None = None
_cached_at: float = 0.0


def _frontmost_app() -> str | None:

    global _cached_app, _cached_at

    now = time.monotonic()

    if now - _cached_at < _CACHE_TTL_SECONDS:
        return _cached_app

    try:

        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ],
            capture_output=True,
            text=True,
            timeout=1,
        )

        _cached_app = result.stdout.strip() or None

    except Exception:

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
