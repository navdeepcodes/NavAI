"""Launching apps, opening URLs, and power actions — per platform.

Callers (tools/system, tools/browser) only ever call the functions in this
module. All platform.system() branching lives here.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from hostplatform import current_platform

# Common Linux browser binaries to try when the configured DEFAULT_BROWSER
# isn't an installed binary name (it defaults to "Opera", which most Linux
# machines won't have — falling straight to NotImplementedError there would
# make open_url dead on arrival on a fresh Linux box).
_LINUX_BROWSER_FALLBACKS = [
    "firefox",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "brave-browser",
]


def _linux_browser_binary(configured_name: str) -> str | None:
    direct = shutil.which(configured_name) or shutil.which(
        configured_name.lower().replace(" ", "-")
    )
    if direct:
        return direct
    for candidate in _LINUX_BROWSER_FALLBACKS:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _find_desktop_entry(name: str) -> str | None:
    """Best-effort match of an app name to an installed .desktop file id."""
    needle = name.lower().replace(" ", "")
    search_dirs = [
        Path.home() / ".local/share/applications",
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
    ]
    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for entry in directory.glob("*.desktop"):
            stem = entry.stem.lower().replace(" ", "")
            if needle in stem or stem in needle:
                return entry.name
    return None


# ---------------------------------------------------------------------------
# Open application
# ---------------------------------------------------------------------------

def open_application(name: str, path: str | None = None) -> str:
    if not name or not name.strip():
        raise ValueError("Application name is required.")
    name = name.strip()
    system = current_platform()

    if system == "Darwin":
        command = ["open", "-a", name] + ([path] if path else [])
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                (result.stderr or "").strip() or f"Could not open '{name}'. Is it installed?"
            )
        return f"Opened {path} in {name}." if path else f"Opened {name}."

    if system == "Linux":
        binary = shutil.which(name) or shutil.which(name.lower().replace(" ", "-"))
        if binary:
            subprocess.Popen(
                [binary] + ([path] if path else []),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Opened {path} in {name}." if path else f"Opened {name}."

        desktop_id = _find_desktop_entry(name)
        if desktop_id:
            launcher = "gio" if shutil.which("gio") else ("gtk-launch" if shutil.which("gtk-launch") else None)
            if launcher is None:
                raise RuntimeError(
                    f"Found a desktop entry for '{name}' but neither gio nor gtk-launch is installed."
                )
            args = (["gio", "launch", desktop_id] if launcher == "gio" else ["gtk-launch", desktop_id])
            if path:
                args.append(path)
            result = subprocess.run(args, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    (result.stderr or "").strip() or f"Could not open '{name}'. Is it installed?"
                )
            return f"Opened {path} in {name}." if path else f"Opened {name}."

        raise RuntimeError(
            f"Could not find an executable or desktop entry for '{name}'. Is it installed?"
        )

    raise NotImplementedError(f"Opening applications is not implemented on {system}.")


# ---------------------------------------------------------------------------
# Browser / URL
# ---------------------------------------------------------------------------

def open_browser(default_browser: str) -> str:
    system = current_platform()

    if system == "Darwin":
        subprocess.run(["open", "-a", default_browser], check=True)
        return "Browser opened successfully."

    if system == "Linux":
        binary = _linux_browser_binary(default_browser)
        if binary is None:
            raise RuntimeError(
                f"No browser found. Tried '{default_browser}' and the common Linux browsers "
                f"({', '.join(_LINUX_BROWSER_FALLBACKS)}); none are installed."
            )
        subprocess.Popen([binary], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Browser opened successfully."

    raise NotImplementedError(f"Opening a browser is not implemented on {system}.")


def open_url(url: str, default_browser: str) -> str:
    system = current_platform()

    if system == "Darwin":
        subprocess.run(["open", "-a", default_browser, url], check=True)
        return f"Opened {url}"

    if system == "Linux":
        binary = _linux_browser_binary(default_browser)
        if binary is not None:
            subprocess.Popen([binary, url], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opened {url}"
        if shutil.which("xdg-open"):
            subprocess.run(["xdg-open", url], check=True)
            return f"Opened {url}"
        raise RuntimeError(
            f"No browser or xdg-open found to open '{url}'. Tried '{default_browser}' and the "
            f"common Linux browsers ({', '.join(_LINUX_BROWSER_FALLBACKS)})."
        )

    raise NotImplementedError(f"Opening a URL is not implemented on {system}.")


# ---------------------------------------------------------------------------
# Power actions
# ---------------------------------------------------------------------------

def lock() -> str:
    system = current_platform()
    if system == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], check=True)
    elif system == "Windows":
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
    elif system == "Linux":
        if shutil.which("loginctl"):
            subprocess.run(["loginctl", "lock-session"], check=True)
        elif shutil.which("xdg-screensaver"):
            subprocess.run(["xdg-screensaver", "lock"], check=True)
        else:
            raise NotImplementedError("No session lock mechanism (loginctl/xdg-screensaver) found.")
    else:
        raise NotImplementedError("Lock not supported on this OS.")
    return "Screen locked."


def sleep() -> str:
    system = current_platform()
    if system == "Darwin":
        subprocess.run(["pmset", "sleepnow"], check=True)
    elif system == "Linux":
        if shutil.which("systemctl"):
            subprocess.run(["systemctl", "suspend"], check=True)
        else:
            raise NotImplementedError("systemctl not found; cannot suspend.")
    else:
        raise NotImplementedError("Sleep not supported on this OS.")
    return "Computer sleeping."


def shutdown() -> str:
    system = current_platform()
    if system == "Darwin":
        subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
    elif system == "Windows":
        subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
    elif system == "Linux":
        if shutil.which("systemctl"):
            subprocess.run(["systemctl", "poweroff"], check=True)
        else:
            subprocess.run(["shutdown", "-h", "now"], check=True)
    else:
        raise NotImplementedError("Shutdown not supported on this OS.")
    return "Shutdown initiated."


def restart() -> str:
    system = current_platform()
    if system == "Darwin":
        subprocess.run(["sudo", "shutdown", "-r", "now"], check=True)
    elif system == "Windows":
        subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
    elif system == "Linux":
        if shutil.which("systemctl"):
            subprocess.run(["systemctl", "reboot"], check=True)
        else:
            subprocess.run(["shutdown", "-r", "now"], check=True)
    else:
        raise NotImplementedError("Restart not supported on this OS.")
    return "Restart initiated."
