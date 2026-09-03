"""Shared motion timing for the Home surface.

Motion communicates state, so the frame budget is deliberately small: nothing
here runs faster than 30fps, idle drifts at 12fps, and any widget that isn't
visible stops ticking entirely.
"""
from __future__ import annotations

import subprocess

# Frame intervals in milliseconds.
ACTIVE_INTERVAL = 33   # ~30fps, used while Mike is doing something
IDLE_INTERVAL = 83     # ~12fps, enough for a slow breathe

_reduced: bool | None = None


def reduced_motion() -> bool:
    """
    True when macOS accessibility asks for reduced motion. Cached — the setting
    doesn't change often enough to justify shelling out on every frame.
    """

    global _reduced

    if _reduced is not None:
        return _reduced

    try:
        result = subprocess.run(
            ["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        _reduced = result.stdout.strip() == "1"
    except Exception:
        _reduced = False

    return _reduced


def ease_in_out(t: float) -> float:
    """Smoothstep over 0..1."""

    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))
