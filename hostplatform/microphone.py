"""Windows microphone privacy check for desktop apps.

Windows never prompts desktop (Win32) apps for microphone access. If
Settings → Privacy → Microphone → "Let desktop apps access your
microphone" is off, voice input is silently dead — no prompt, no error.

This reads what Settings reads:
  HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\
    ConsentStore\\microphone  (Value, and NonPackaged\\Value)

"Deny" means blocked. Anything else / missing / non-Windows means unknown
or allowed — never claim blocked unless we saw "Deny".
"""
from __future__ import annotations

import platform
import subprocess


def status() -> str:
    """One of "denied" | "allowed" | "unknown". Never raises."""
    if platform.system() != "Windows":
        return "unknown"
    try:
        import winreg
        base = (
            r"Software\Microsoft\Windows\CurrentVersion"
            r"\CapabilityAccessManager\ConsentStore\microphone"
        )

        def _read(path: str, name: str = "Value") -> str | None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                    value, _ = winreg.QueryValueEx(key, name)
                    return str(value)
            except OSError:
                return None

        # Either the packaged or the non-packaged desktop entry denying
        # is enough to silence us.
        main = _read(base)
        nonpackaged = _read(base + r"\NonPackaged")
        if main == "Deny" or nonpackaged == "Deny":
            return "denied"
        if main == "Allow" or nonpackaged == "Allow":
            return "allowed"
        return "unknown"
    except Exception:
        return "unknown"


def open_settings() -> bool:
    """Open the Windows microphone privacy page. True if launched."""
    try:
        if platform.system() == "Windows":
            import os
            os.startfile("ms-settings:privacy-microphone")  # type: ignore[attr-defined]
            return True
        if platform.system() == "Darwin":
            subprocess.run(
                ["open",
                 "x-apple.systempreferences:com.apple.preference.security"
                 "?Privacy_Microphone"],
                check=False,
            )
            return True
    except Exception:
        return False
    return False
