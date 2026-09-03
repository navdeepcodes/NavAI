from __future__ import annotations

import platform
import subprocess


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

    if not name or not name.strip():
        raise ValueError("Application name is required.")

    name = name.strip()
    system = platform.system()

    if system != "Darwin":
        raise NotImplementedError(
            "Opening applications is only implemented for macOS."
        )

    command = ["open", "-a", name]

    if path:
        command.append(path)

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        message = (result.stderr or "").strip()
        raise RuntimeError(
            message or f"Could not open '{name}'. Is it installed?"
        )

    if path:
        return f"Opened {path} in {name}."

    return f"Opened {name}."


# ---------------------------------------------------------
# Lock Screen
# ---------------------------------------------------------

def lock() -> str:

    system = platform.system()

    if system == "Darwin":

        subprocess.run(

            [
                "pmset",
                "displaysleepnow"
            ],

            check=True

        )

    elif system == "Windows":

        subprocess.run(

            [
                "rundll32.exe",
                "user32.dll,LockWorkStation"
            ],

            check=True

        )

    else:

        raise NotImplementedError(
            "Lock not supported on this OS."
        )

    return "Screen locked."


# ---------------------------------------------------------
# Sleep
# ---------------------------------------------------------

def sleep() -> str:

    system = platform.system()

    if system == "Darwin":

        subprocess.run(

            [
                "pmset",
                "sleepnow"
            ],

            check=True

        )

    elif system == "Windows":

        raise NotImplementedError(
            "Sleep not implemented for Windows."
        )

    else:

        raise NotImplementedError(
            "Sleep not supported."
        )

    return "Computer sleeping."


# ---------------------------------------------------------
# Shutdown
# ---------------------------------------------------------

def shutdown() -> str:

    system = platform.system()

    if system == "Darwin":

        subprocess.run(

            [
                "sudo",
                "shutdown",
                "-h",
                "now"
            ],

            check=True

        )

    elif system == "Windows":

        subprocess.run(

            [
                "shutdown",
                "/s",
                "/t",
                "0"
            ],

            check=True

        )

    else:

        raise NotImplementedError()

    return "Shutdown initiated."


# ---------------------------------------------------------
# Restart
# ---------------------------------------------------------

def restart() -> str:

    system = platform.system()

    if system == "Darwin":

        subprocess.run(

            [
                "sudo",
                "shutdown",
                "-r",
                "now"
            ],

            check=True

        )

    elif system == "Windows":

        subprocess.run(

            [
                "shutdown",
                "/r",
                "/t",
                "0"
            ],

            check=True

        )

    else:

        raise NotImplementedError()

    return "Restart initiated."