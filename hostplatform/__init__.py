"""Platform abstraction layer.

Everything above this package (brain/, tools/, ui/, voice/, vision/) talks to
the functions in hostplatform.* and never branches on platform.system()
itself. Each hostplatform module owns its own Darwin/Linux (/Windows, once
that work lands) dispatch internally, so adding a platform means touching
this package, not scattering `if darwin` checks through the app.
"""
from __future__ import annotations

import platform


def current_platform() -> str:
    """'Darwin', 'Linux', or 'Windows' — matches platform.system()."""
    return platform.system()


def is_macos() -> bool:
    return current_platform() == "Darwin"


def is_linux() -> bool:
    return current_platform() == "Linux"


def is_windows() -> bool:
    return current_platform() == "Windows"
