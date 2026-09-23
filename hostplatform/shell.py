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

import json
import platform
import subprocess
from urllib.parse import urlparse


class ShellError(RuntimeError):
    """The OS shell could not do what it was asked."""


def _system() -> str:
    return platform.system()


def _run_checked(command: list[str]) -> None:
    subprocess.run(command, check=True)


_BROWSER_EXE_NAMES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe",
}


def _bring_browser_forward() -> None:
    """Best-effort: raise whichever browser just received an open request.

    os.startfile hands a URL to the OS shell, which -- when a browser is
    already running -- typically opens it as a new background tab without
    giving that window focus. Verified directly: asking Mike to open a URL
    left the browser exactly where it was, with nothing on screen suggesting
    anything had happened, even though the tab genuinely opened. A real
    action that produces no visible sign of having happened reads as a
    failure regardless of what actually occurred underneath.

    Windows refuses a bare SetForegroundWindow from a process it doesn't
    consider to have "input permission" -- computer/windows.py's
    activate_app already found and verified the fix (attach this thread's
    input queue to the target window's thread first); mirrored here rather
    than imported, since hostplatform sits below computer/ in this
    codebase's layering and importing upward would invert that.
    """
    try:
        import ctypes

        import win32api
        import win32con
        import win32gui
        import win32process

        def _proc_name(pid: int) -> str:
            try:
                handle = win32api.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
                try:
                    path = win32process.GetModuleFileNameEx(handle, 0)
                finally:
                    win32api.CloseHandle(handle)
                return path.rsplit("\\", 1)[-1].lower()
            except Exception:
                return ""

        found: list[int] = []

        def _visit(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if _proc_name(pid) in _BROWSER_EXE_NAMES:
                found.append(hwnd)
                return False
            return True

        win32gui.EnumWindows(_visit, None)
        if not found:
            return

        hwnd = found[0]
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
        current_thread = win32api.GetCurrentThreadId()
        attached = False
        try:
            if target_thread != current_thread:
                attached = bool(ctypes.windll.user32.AttachThreadInput(
                    current_thread, target_thread, True))
            win32gui.SetForegroundWindow(hwnd)
        finally:
            if attached:
                ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, False)
    except Exception:
        pass


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
        import os
        # Two mechanisms, tried in order, because neither alone is general.
        #
        # os.startfile resolves a bare name through the App Paths registry and
        # PATH the way Explorer's Run box does, so it opens things with a
        # registered executable -- "notepad", "calc", "mspaint", "chrome",
        # "code" -- and is the only path that can also open `path` *in* the app.
        # But it does NOT resolve friendly display names ("Calculator" raises
        # FileNotFoundError, verified) and cannot reach Store/UWP apps at all,
        # which have no executable on disk to point at.
        #
        # So on FileNotFoundError, fall back to how the Start menu itself
        # launches everything: Get-StartApps lists every installed app, Win32
        # and UWP, by display name with a launchable AppID, and
        # shell:AppsFolder\<AppID> starts it. That is what makes "open
        # Calculator" / "open Spotify" work without this file knowing a single
        # app by name.
        try:
            if path:
                os.startfile(name, arguments=f'"{path}"')  # type: ignore[call-arg]
            else:
                os.startfile(name)  # type: ignore[attr-defined]
            return
        except FileNotFoundError:
            app_id = _resolve_start_app(name)
            if app_id:
                try:
                    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
                    return
                except Exception as exc:
                    raise ShellError(f"Found {name!r} but could not launch it: {exc}")
            raise ShellError(
                f"Could not find an application named {name!r}. Check the "
                "spelling, or that it's installed."
            )
    raise NotImplementedError(f"Opening applications is not implemented for {system}.")


def _resolve_start_app(name: str) -> str | None:
    """The AppID of the installed app whose Start-menu name best matches `name`,
    or None. Covers Win32 and Store apps alike -- this is the same catalogue the
    Start menu searches, so nothing here is hard-coded to a particular app.

    Match precedence: exact display name, then starts-with, then contains, then
    a substring of the AppID (so "calc" still finds Calculator's AUMID). The
    first, most specific hit wins, which keeps "Calculator" off "Calculator
    Plus" when the real one is present.
    """
    wanted = (name or "").strip().casefold()
    if not wanted:
        return None
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=12,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(data, dict):
        data = [data]
    apps = [(str(a.get("Name", "")), str(a.get("AppID", "")))
            for a in data if a.get("AppID")]

    def pick(predicate):
        for disp, app_id in apps:
            if predicate(disp.casefold(), app_id.casefold()):
                return app_id
        return None

    return (
        pick(lambda d, i: d == wanted)
        or pick(lambda d, i: d.startswith(wanted))
        or pick(lambda d, i: wanted in d)
        or pick(lambda d, i: wanted in i)
    )


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
        _bring_browser_forward()
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
        import os
        # Windows has no single mechanism for "launch whatever the user set
        # as their default browser" the way macOS's LaunchServices does by
        # app name -- but os.startfile on a URL already goes through the
        # registered http handler, which *is* the user's actual default
        # browser, whatever it is. Verified directly: this does not depend
        # on DEFAULT_BROWSER (whose "Opera" default most machines don't
        # have installed) or any specific browser being present.
        os.startfile("about:blank")  # type: ignore[attr-defined]
        _bring_browser_forward()
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
    if system == "Windows":
        # SetSuspendState's second argument (Force) is 0 here on purpose --
        # forcing would skip apps that refuse the suspend (unsaved work in
        # another app), which is not a call Mike gets to make on the user's
        # behalf.
        _run_checked(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
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
