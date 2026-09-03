"""System-wide hotkey for summoning Mike from anywhere.

Uses Carbon's RegisterEventHotKey rather than an NSEvent global monitor: the
Carbon route needs no Accessibility permission, so Mike is reachable the moment
the app launches instead of after a trip through System Settings.

The Carbon handler is dispatched by the same CFRunLoop Qt drives on macOS, so
the callback lands on the GUI thread and can touch widgets directly.
"""
from __future__ import annotations

import ctypes
import ctypes.util
from typing import Callable

from logs.logger import logger

# Carbon modifier masks (Events.h)
CMD = 0x0100
SHIFT = 0x0200
OPTION = 0x0800
CONTROL = 0x1000

# Virtual key codes (Events.h)
KEY_SPACE = 49
KEY_M = 46

_EVENT_CLASS_KEYBOARD = 0x6B657962  # 'keyb'
_EVENT_HOTKEY_PRESSED = 5
_SIGNATURE = 0x4D494B45  # 'MIKE'


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


_HANDLER = ctypes.CFUNCTYPE(
    ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)


class GlobalHotkey:
    """
    Registers one system-wide key combination. Failure is never fatal — Mike
    simply stays reachable by its other surfaces.
    """

    def __init__(
        self,
        on_pressed: Callable[[], None],
        key_code: int = KEY_SPACE,
        modifiers: int = CMD | SHIFT,
    ) -> None:
        self._on_pressed = on_pressed
        self._key_code = key_code
        self._modifiers = modifiers

        self._carbon = None
        self._hotkey_ref = ctypes.c_void_p()
        self._handler_ref = ctypes.c_void_p()
        self._callback = None          # must outlive registration
        self._registered = False

    # ── Lifecycle ────────────────────────────────────────────

    def register(self) -> bool:
        if self._registered:
            return True

        try:
            path = ctypes.util.find_library("Carbon")
            if not path:
                logger.warning("Global hotkey unavailable: Carbon not found.")
                return False

            carbon = ctypes.CDLL(path)
            self._carbon = carbon

            carbon.GetApplicationEventTarget.restype = ctypes.c_void_p

            def _fired(next_handler, event, user_data) -> int:
                try:
                    self._on_pressed()
                except Exception:
                    logger.exception("Global hotkey handler failed.")
                return 0

            self._callback = _HANDLER(_fired)

            spec = _EventTypeSpec(_EVENT_CLASS_KEYBOARD, _EVENT_HOTKEY_PRESSED)
            target = carbon.GetApplicationEventTarget()

            status = carbon.InstallEventHandler(
                ctypes.c_void_p(target),
                self._callback,
                1,
                ctypes.byref(spec),
                None,
                ctypes.byref(self._handler_ref),
            )
            if status != 0:
                logger.warning("Global hotkey: InstallEventHandler failed (%s).", status)
                return False

            hotkey_id = _EventHotKeyID(_SIGNATURE, 1)
            status = carbon.RegisterEventHotKey(
                ctypes.c_uint32(self._key_code),
                ctypes.c_uint32(self._modifiers),
                hotkey_id,
                ctypes.c_void_p(target),
                0,
                ctypes.byref(self._hotkey_ref),
            )
            if status != 0:
                logger.warning("Global hotkey: RegisterEventHotKey failed (%s).", status)
                return False

            self._registered = True
            logger.info("Global hotkey registered (%s).", self.describe())
            return True

        except Exception:
            logger.exception("Global hotkey registration failed.")
            return False

    def unregister(self) -> None:
        if not self._registered or self._carbon is None:
            return
        try:
            if self._hotkey_ref:
                self._carbon.UnregisterEventHotKey(self._hotkey_ref)
            if self._handler_ref:
                self._carbon.RemoveEventHandler(self._handler_ref)
        except Exception:
            logger.exception("Global hotkey teardown failed.")
        finally:
            self._registered = False

    # ── Description ──────────────────────────────────────────

    def is_registered(self) -> bool:
        return self._registered

    def describe(self) -> str:
        parts = []
        if self._modifiers & CONTROL:
            parts.append("Control")
        if self._modifiers & OPTION:
            parts.append("Option")
        if self._modifiers & SHIFT:
            parts.append("Shift")
        if self._modifiers & CMD:
            parts.append("Command")

        names = {KEY_SPACE: "Space", KEY_M: "M"}
        parts.append(names.get(self._key_code, f"key {self._key_code}"))
        return " + ".join(parts)
