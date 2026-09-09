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
    shell.open_application(name, path)

    if path:
        return f"Opened {path} in {name}."
    return f"Opened {name}."


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
