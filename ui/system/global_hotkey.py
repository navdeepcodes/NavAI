"""System-wide hotkey for summoning Mike from anywhere.

The actual mechanism (Carbon's RegisterEventHotKey on macOS) lives in
hostplatform.desktop, alongside every other OS-facing desktop-presence
service. This module stays as its own file and keeps the exact `GlobalHotkey`
name and shape ui/app.py imports and tests reach into directly
(`window.hotkey._registered`), so the platform split underneath it is
invisible to both.

Construction never raises, on any platform — ui/app.py constructs this
unconditionally, outside the `_optional()` guard that wraps `.register()`.
An OS with no hotkey backend yet is a `.register()` failure, exactly like a
Carbon call failing, not a startup crash.
"""
from __future__ import annotations

from typing import Callable

from hostplatform import desktop
from logs.logger import logger


class GlobalHotkey:
    """
    Registers one system-wide key combination. Failure is never fatal — Mike
    simply stays reachable by its other surfaces.
    """

    def __init__(
        self,
        on_pressed: Callable[[], None],
        key_code: int | None = None,
        modifiers: int | None = None,
    ) -> None:
        self._on_pressed = on_pressed
        self._key_code = key_code
        self._modifiers = modifiers
        self._backend: desktop._HotkeyBackend | None = None

    # ── Lifecycle ────────────────────────────────────────────

    def register(self) -> bool:
        if self._backend is None:
            try:
                self._backend = desktop.make_hotkey(
                    self._on_pressed, key_code=self._key_code, modifiers=self._modifiers)
            except desktop.HotkeyUnavailable as exc:
                logger.warning("Global hotkey unavailable: %s", exc)
                return False
        return self._backend.register()

    def unregister(self) -> None:
        if self._backend is not None:
            self._backend.unregister()

    # ── Description ──────────────────────────────────────────

    def is_registered(self) -> bool:
        return self._backend.is_registered() if self._backend is not None else False

    @property
    def _registered(self) -> bool:
        """Kept for the lifecycle tests, which read this attribute directly
        rather than calling is_registered()."""
        return self.is_registered()

    def describe(self) -> str:
        if self._backend is None:
            return "unavailable"
        return self._backend.describe()
