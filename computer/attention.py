"""Where Mike is working on the screen -- said, so the interface can show it.

When Mike clicks, types, scrolls or brings another app forward, the action
tells whoever is listening *where* (screen pixels) and *what* ("Clicking
Save"), just before it happens. The interface's guide draws the nib flying
there; nothing here knows about it, and with no listener every call is a
no-op, so tests and headless runs are unaffected.

Calls come from Mike's worker thread. `point` waits (briefly, never more than
MAX_WAIT) for the nib to arrive, so it lands before the click does; the rest
don't wait. Nothing here can raise or hold an action up.
"""
from __future__ import annotations

from typing import Callable

#: The longest an action waits for the nib to get there.
MAX_WAIT = 0.9

#: listener(kind, x, y, label) -> seconds until the nib arrives (0 = already
#: there / nothing to wait for). kind: "click" | "type" | "scroll" | "key" |
#: "window". x, y are screen pixels (physical), or None to stay where it is.
Listener = Callable[[str, "int | None", "int | None", str], float]

_listener: Listener | None = None


def set_listener(listener: Listener | None) -> None:
    global _listener
    _listener = listener


def active() -> bool:
    return _listener is not None


def point(kind: str, x: int | None, y: int | None, label: str = "") -> None:
    """Mike is about to act at (x, y). Returns once the nib has arrived
    (at most MAX_WAIT), so the action follows it rather than beating it."""
    listener = _listener
    if listener is None:
        return
    try:
        wait = float(listener(kind, None if x is None else int(x),
                              None if y is None else int(y), label or ""))
    except Exception:
        return
    if wait > 0:
        import time
        time.sleep(min(wait, MAX_WAIT))


def window(bounds, label: str = "") -> None:
    """Mike brought a window forward: point at its title bar. `bounds` is
    anything with x, y, width, height (a computer.base.Bounds)."""
    try:
        x = int(bounds.x + bounds.width / 2)
        y = int(bounds.y + min(18, bounds.height / 2))
    except Exception:
        return
    point("window", x, y, label)
