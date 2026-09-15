from __future__ import annotations

from hostplatform import desktop


# ---------------------------------------------------------
# Open Application
# ---------------------------------------------------------

def open_application(name: str, path: str | None = None) -> str:
    """
    Launch or focus an application by name. Generic on purpose — nothing
    here knows about any particular app.

    Args:
        name: Application name, e.g. "Visual Studio Code", "Safari".
        path: Optional file or folder to open with it.
    """
    return desktop.open_application(name, path)


# ---------------------------------------------------------
# Lock Screen
# ---------------------------------------------------------

def lock() -> str:
    return desktop.lock()


# ---------------------------------------------------------
# Sleep
# ---------------------------------------------------------

def sleep() -> str:
    return desktop.sleep()


# ---------------------------------------------------------
# Shutdown
# ---------------------------------------------------------

def shutdown() -> str:
    return desktop.shutdown()


# ---------------------------------------------------------
# Restart
# ---------------------------------------------------------

def restart() -> str:
    return desktop.restart()
