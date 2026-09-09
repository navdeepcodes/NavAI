"""Ask the OS to open something, or manage its session, on Mike's behalf.

This groups a pattern that was scattered across tools/system/actions.py and
tools/browser/open_*.py: `if Darwin: subprocess.run([...]) elif Windows:
subprocess.run([...])`, with a *tool* deciding for itself how each OS opens
a browser or locks the screen. That is exactly the leak Phase 2 of the
Windows-transition audit names — high-level code should ask for an outcome,
not know the mechanism.

Everything here is a fire-and-forget request to the OS shell or session
manager — opening a URL, a file, an application, locking the screen — not an
interaction with a running application's own UI. That distinction is what
separates this module from computer/ (UI Automation / Accessibility control
of an already-open window's controls).

Windows honesty note: the URL/file/browser paths below use `os.startfile`,
the documented, dependency-free mechanism — not the `start` shell builtin the
previous unverified code used, which mishandles a URL as `start`'s window
title unless an empty title is passed first. This is a correction made from
Windows' documented behaviour, not a guess dressed up as a fix, but it has
not yet been run on a physical Windows machine — see the capability contract
once that verification happens. `open_application` is left unimplemented for
Windows on purpose: Windows has no single LaunchServices-equivalent for
resolving a friendly app name to an executable, and a fabricated one would be
worse than an honest gap.
"""
from __future__ import annotations

import platform
import subprocess
from urllib.parse import urlparse


class ShellError(RuntimeError):
    """The OS shell could not do what it was asked."""


def _system() -> str:
    return platform.system()


def _run_checked(command: list[str]) -> None:
    subprocess.run(command, check=True)


def normalize_url(url: str) -> str:
    url = url.strip()
    if not urlparse(url).scheme:
        url = f"https://{url}"
    return url


# ── opening things ─────────────────────────────────────────

def open_application(name: str, path: str | None = None) -> None:
    """Launch or focus an application by name, optionally with a file/folder
    to open in it."""
    system = _system()
    if system == "Darwin":
        command = ["open", "-a", name]
        if path:
            command.append(path)
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            message = (result.stderr or "").strip()
            raise ShellError(message or f"Could not open {name!r}. Is it installed?")
        return
    if system == "Windows":
        raise NotImplementedError(
            "Opening an application by name is not implemented on Windows "
            "yet. Windows has no single mechanism equivalent to macOS "
            "LaunchServices for resolving a friendly app name to an "
            "executable; a real implementation needs one of the Start Menu "
            "shortcut index or the registry's App Paths, verified on the "
            "physical machine — not shipped as a guess."
        )
    raise NotImplementedError(f"Opening applications is not implemented for {system}.")


def open_url(url: str) -> None:
    """Open a URL with the configured browser (macOS) or the OS default
    handler (Windows, Linux)."""
    url = normalize_url(url)
    system = _system()
    if system == "Darwin":
        from config.settings import DEFAULT_BROWSER
        _run_checked(["open", "-a", DEFAULT_BROWSER, url])
        return
    if system == "Windows":
        import os
        os.startfile(url)  # type: ignore[attr-defined]
        return
    _run_checked(["xdg-open", url])


def open_path(path: str) -> None:
    """Open a file or folder with the OS's default handler."""
    system = _system()
    if system == "Darwin":
        _run_checked(["open", path])
        return
    if system == "Windows":
        import os
        os.startfile(path)  # type: ignore[attr-defined]
        return
    _run_checked(["xdg-open", path])


def open_browser() -> None:
    """Open the configured default browser with no URL."""
    system = _system()
    if system == "Darwin":
        from config.settings import DEFAULT_BROWSER
        _run_checked(["open", "-a", DEFAULT_BROWSER])
        return
    if system == "Windows":
        from config.settings import DEFAULT_BROWSER
        import os
        # App Paths resolves a bare executable name (e.g. "msedge") the same
        # way Explorer's Run box does, which os.startfile goes through.
        os.startfile(DEFAULT_BROWSER)  # type: ignore[attr-defined]
        return
    from config.settings import DEFAULT_BROWSER
    _run_checked([DEFAULT_BROWSER])


# ── session/power state ─────────────────────────────────────

def lock_screen() -> None:
    system = _system()
    if system == "Darwin":
        _run_checked(["pmset", "displaysleepnow"])
        return
    if system == "Windows":
        _run_checked(["rundll32.exe", "user32.dll,LockWorkStation"])
        return
    raise NotImplementedError(f"Locking the screen is not implemented for {system}.")


def sleep_now() -> None:
    system = _system()
    if system == "Darwin":
        _run_checked(["pmset", "sleepnow"])
        return
    raise NotImplementedError(f"Sleep is not implemented for {system}.")


def shutdown_now() -> None:
    system = _system()
    if system == "Darwin":
        _run_checked(["sudo", "shutdown", "-h", "now"])
        return
    if system == "Windows":
        _run_checked(["shutdown", "/s", "/t", "0"])
        return
    raise NotImplementedError(f"Shutdown is not implemented for {system}.")


def restart_now() -> None:
    system = _system()
    if system == "Darwin":
        _run_checked(["sudo", "shutdown", "-r", "now"])
        return
    if system == "Windows":
        _run_checked(["shutdown", "/r", "/t", "0"])
        return
    raise NotImplementedError(f"Restart is not implemented for {system}.")
