from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    """
    Permission categories used by tools.

    Each tool declares the permission it requires.
    The PermissionManager decides whether the action
    is allowed, requires confirmation, or is blocked.
    """

    FILESYSTEM = "filesystem"

    BROWSER = "browser"

    TERMINAL = "terminal"

    SYSTEM = "system"

    EMAIL = "email"

    CLIPBOARD = "clipboard"

    CAMERA = "camera"

    MICROPHONE = "microphone"

    KEYBOARD = "keyboard"

    MOUSE = "mouse"

    @classmethod
    def values(cls) -> list[str]:
        """
        Return all permission names.
        """

        return [permission.value for permission in cls]