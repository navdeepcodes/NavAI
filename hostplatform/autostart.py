"""Open Mike when you sign in — the Windows way (HKCU\\...\\Run).

Only offered for the installed, packaged app on Windows: registering a
development checkout (a Python interpreter and a script path) to start at
every sign-in would be surprising and fragile. The Run entry launches Mike with
--autostart, so he takes the corner quietly instead of opening the workspace
over whatever the user is doing.
"""
from __future__ import annotations

import platform
import sys

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "Mike"


def supported() -> bool:
    return platform.system() == "Windows" and bool(getattr(sys, "frozen", False))


def _command() -> str:
    return f'"{sys.executable}" --autostart'


def is_enabled() -> bool:
    if not supported():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as key:
            value, _ = winreg.QueryValueEx(key, _NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    """Add or remove the sign-in entry. True if the system now matches `on`."""
    if not supported():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, _NAME)
                except FileNotFoundError:
                    pass
        return is_enabled() == on
    except OSError:
        return False
