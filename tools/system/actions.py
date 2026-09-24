from __future__ import annotations

from hostplatform import shell


# ---------------------------------------------------------
# Open Application
# ---------------------------------------------------------

def open_application(name: str, path: str | None = None) -> str:
    """
    Launch or focus an application by name. Generic on purpose — nothing
    here knows about any particular app; the OS mechanism for it lives in
    hostplatform.shell.

    Args:
        name: Application name, e.g. "Visual Studio Code", "Safari".
        path: Optional file or folder to open with it.
    """
    if not name or not name.strip():
        raise ValueError("Application name is required.")

    name = name.strip()
    before = _window_ids()
    shell.open_application(name, path)

    # Launching is not opening. A process can start and never show a window
    # (a bad name that resolved to something else, an app that fails at
    # start-up, one still loading), and "Opened X" is a claim the user acts
    # on. So it is only made once a window for it is actually seen.
    window = _wait_for_window(name, before)
    if window is None:
        return (
            f"Launched {name}, but no window for it has appeared yet — it may "
            "still be starting, or it may not have opened. Check with "
            "list_windows before relying on it."
        )
    target = f"{path} in {name}" if path else name
    return f"Opened {target} — its window “{window}” is open."


# How long to wait for a launched app's window. Most apps show one in well
# under a second; a cold Word or VS Code can take several.
OPEN_WINDOW_TIMEOUT = 8.0


def _controller():
    try:
        from computer.session import SESSION
        ok, _ = SESSION.availability()
        return SESSION.controller() if ok else None
    except Exception:
        return None


def _window_ids() -> set:
    controller = _controller()
    if controller is None:
        return set()
    try:
        return {w.window_id for w in controller.list_windows()}
    except Exception:
        return set()


def _wait_for_window(name: str, before: set, timeout: float = OPEN_WINDOW_TIMEOUT) -> str | None:
    """The title of the window the launch produced, or None if none appeared.

    Accepts a window whose app or title carries the name ("notepad",
    "Calculator", "... - Visual Studio Code"), or any new window that has come
    to the front since the launch -- nothing here knows a particular app.
    """
    import time

    controller = _controller()
    if controller is None:
        return None
    wanted = name.casefold()
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            windows = controller.list_windows()
        except Exception:
            return None
        for w in windows:
            named = wanted in (w.app or "").casefold() or wanted in (w.title or "").casefold()
            new_in_front = w.frontmost and w.window_id not in before
            if (named and (w.window_id not in before or w.frontmost)) or new_in_front:
                return w.title or w.app
        time.sleep(0.2)
    return None


# ---------------------------------------------------------
# Lock Screen
# ---------------------------------------------------------

def lock() -> str:
    shell.lock_screen()
    return "Screen locked."


# ---------------------------------------------------------
# Sleep
# ---------------------------------------------------------

def sleep() -> str:
    shell.sleep_now()
    return "Computer sleeping."


# ---------------------------------------------------------
# Shutdown
# ---------------------------------------------------------

def shutdown() -> str:
    shell.shutdown_now()
    return "Shutdown initiated."


# ---------------------------------------------------------
# Restart
# ---------------------------------------------------------

def restart() -> str:
    shell.restart_now()
    return "Restart initiated."
