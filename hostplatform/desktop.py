"""Desktop-presence mechanics: the global hotkey and reduced-motion.

Frontmost-app detection is deliberately *not* here — it used to live in
brain/environment.py as its own osascript call, which was a second,
independent (and worse: Automation-gated, TCC-prompting) implementation of a
question computer/base.py's ComputerController already answers correctly.
That call site now reuses `get_controller().frontmost_app()` directly rather
than gaining a third copy of the same logic in this module. Not every
OS-facing question needs its own hostplatform service — some of them are
already someone else's job.
"""
from __future__ import annotations

import ctypes
import platform
import subprocess
from typing import Callable


class _MSG(ctypes.Structure):
    """The Win32 MSG struct — only defined so _WindowsHotkey can read
    .message/.wParam out of the raw pointer Qt's native event filter hands
    it. Harmless to define on any OS; ctypes.windll, not this, is what
    would fail off Windows."""
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint32),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


class HotkeyUnavailable(Exception):
    """No global-hotkey backend exists for this platform yet."""


def make_hotkey(on_pressed: Callable[[], None], *, key_code: int | None = None,
                modifiers: int | None = None) -> "_HotkeyBackend":
    """The one global-hotkey backend for this OS.

    Raises `HotkeyUnavailable` rather than returning a stub — the caller
    (ui/system/global_hotkey.py) treats that exactly like any other
    registration failure: logged, and Mike stays reachable by its other
    surfaces. `key_code`/`modifiers` are backend-specific (macOS virtual key
    codes and Carbon modifier masks) — passing None lets the backend use its
    own sensible default rather than this module inventing a
    platform-agnostic key-combination format that would mean nothing on the
    OS actually receiving it.
    """
    system = platform.system()
    if system == "Darwin":
        return _DarwinHotkey(on_pressed, key_code, modifiers)
    if system == "Windows":
        return _WindowsHotkey(on_pressed, key_code, modifiers)
    raise HotkeyUnavailable(f"No global hotkey backend for {system}.")


class _HotkeyBackend:
    """What ui/system/global_hotkey.py's GlobalHotkey needs from a backend."""

    def register(self) -> bool:
        raise NotImplementedError

    def unregister(self) -> None:
        raise NotImplementedError

    def is_registered(self) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError


class _DarwinHotkey(_HotkeyBackend):
    """System-wide hotkey via Carbon's RegisterEventHotKey.

    Not an NSEvent global monitor: the Carbon route needs no Accessibility
    permission, so Mike is reachable the moment the app launches instead of
    after a trip through System Settings. The handler is dispatched by the
    same CFRunLoop Qt drives on macOS, so the callback lands on the GUI
    thread and can touch widgets directly.
    """

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

    def __init__(self, on_pressed: Callable[[], None],
                 key_code: int | None, modifiers: int | None) -> None:
        import ctypes
        import ctypes.util  # noqa: F401 -- registers ctypes.util as an attribute

        self._ctypes = ctypes
        self._on_pressed = on_pressed
        self._key_code = self.KEY_SPACE if key_code is None else key_code
        self._modifiers = (self.CMD | self.SHIFT) if modifiers is None else modifiers

        class _EventTypeSpec(ctypes.Structure):
            _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]

        class _EventHotKeyID(ctypes.Structure):
            _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]

        self._EventTypeSpec = _EventTypeSpec
        self._EventHotKeyID = _EventHotKeyID
        self._Handler = ctypes.CFUNCTYPE(
            ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)

        self._carbon = None
        self._hotkey_ref = ctypes.c_void_p()
        self._handler_ref = ctypes.c_void_p()
        self._callback = None          # must outlive registration
        self._registered = False

    def register(self) -> bool:
        from logs.logger import logger

        if self._registered:
            return True

        ctypes = self._ctypes
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

            self._callback = self._Handler(_fired)

            spec = self._EventTypeSpec(self._EVENT_CLASS_KEYBOARD, self._EVENT_HOTKEY_PRESSED)
            target = carbon.GetApplicationEventTarget()

            status = carbon.InstallEventHandler(
                ctypes.c_void_p(target), self._callback, 1,
                ctypes.byref(spec), None, ctypes.byref(self._handler_ref),
            )
            if status != 0:
                logger.warning("Global hotkey: InstallEventHandler failed (%s).", status)
                return False

            hotkey_id = self._EventHotKeyID(self._SIGNATURE, 1)
            status = carbon.RegisterEventHotKey(
                ctypes.c_uint32(self._key_code), ctypes.c_uint32(self._modifiers),
                hotkey_id, ctypes.c_void_p(target), 0, ctypes.byref(self._hotkey_ref),
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
        from logs.logger import logger

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

    def is_registered(self) -> bool:
        return self._registered

    def describe(self) -> str:
        parts = []
        if self._modifiers & self.CONTROL:
            parts.append("Control")
        if self._modifiers & self.OPTION:
            parts.append("Option")
        if self._modifiers & self.SHIFT:
            parts.append("Shift")
        if self._modifiers & self.CMD:
            parts.append("Command")
        names = {self.KEY_SPACE: "Space", self.KEY_M: "M"}
        parts.append(names.get(self._key_code, f"key {self._key_code}"))
        return " + ".join(parts)


class _WindowsHotkey(_HotkeyBackend):
    """System-wide hotkey via RegisterHotKey, wired into Qt's own event loop.

    Registered against no specific window (hwnd=None in RegisterHotKey),
    so WM_HOTKEY is posted to the calling thread's message queue instead —
    the same thread Qt's event loop already pumps on, since register() is
    called from the GUI thread at startup. A QAbstractNativeEventFilter
    installed on the running QApplication is what actually sees it: Qt's
    own loop calls GetMessage/DispatchMessage and hands every native
    message to installed filters before its normal handling, which is
    the documented, supported way to observe a message with no window of
    its own — there is no separate message loop to build.

    Cmd+Shift+Space has no exact Windows equivalent: Win+Space is taken by
    the input-method/keyboard-layout switcher, and Ctrl+Alt+Space is
    already bound to something else on this machine — verified directly
    (RegisterHotKey fails with ERROR_HOTKEY_ALREADY_REGISTERED), not
    assumed free. Ctrl+Shift+Space is the default here, keeping Shift as
    the closest translation of the Mac combination's feel, and registered
    successfully in the same check. If some other application holds it on
    a different machine, RegisterHotKey simply fails and this degrades the
    same way a Carbon failure does, logged and non-fatal.
    """

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000  # one callback per physical press, not one per repeat

    VK_SPACE = 0x20

    WM_HOTKEY = 0x0312

    _HOTKEY_ID = 0xCAFE  # arbitrary, unique among Mike's own registrations

    def __init__(self, on_pressed: Callable[[], None],
                 key_code: int | None, modifiers: int | None) -> None:
        self._on_pressed = on_pressed
        self._vk = self.VK_SPACE if key_code is None else key_code
        self._modifiers = (
            (self.MOD_CONTROL | self.MOD_SHIFT) if modifiers is None else modifiers
        )
        self._registered = False
        self._filter = None

    def register(self) -> bool:
        from logs.logger import logger

        if self._registered:
            return True

        try:
            import ctypes

            from PySide6.QtCore import QAbstractNativeEventFilter
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                logger.warning(
                    "Global hotkey: no QApplication yet — register() must "
                    "run after one exists, since the filter attaches to it."
                )
                return False

            ok = ctypes.windll.user32.RegisterHotKey(
                None, self._HOTKEY_ID,
                self._modifiers | self.MOD_NOREPEAT, self._vk,
            )
            if not ok:
                logger.warning(
                    "Global hotkey: RegisterHotKey failed for %s — likely "
                    "already bound by another application.", self.describe(),
                )
                return False

            hotkey_id = self._HOTKEY_ID
            wm_hotkey = self.WM_HOTKEY
            on_pressed = self._on_pressed

            class _Filter(QAbstractNativeEventFilter):
                def nativeEventFilter(self, event_type, message):
                    if event_type != b"windows_generic_MSG":
                        return False, 0
                    msg = ctypes.cast(
                        int(message), ctypes.POINTER(_MSG)
                    ).contents
                    if msg.message == wm_hotkey and msg.wParam == hotkey_id:
                        try:
                            on_pressed()
                        except Exception:
                            logger.exception("Global hotkey handler failed.")
                        return True, 0
                    return False, 0

            self._filter = _Filter()
            app.installNativeEventFilter(self._filter)
            self._registered = True
            logger.info("Global hotkey registered (%s).", self.describe())
            return True

        except Exception:
            logger.exception("Global hotkey registration failed.")
            return False

    def unregister(self) -> None:
        from logs.logger import logger

        if not self._registered:
            return
        try:
            import ctypes

            from PySide6.QtWidgets import QApplication

            ctypes.windll.user32.UnregisterHotKey(None, self._HOTKEY_ID)
            app = QApplication.instance()
            if app is not None and self._filter is not None:
                app.removeNativeEventFilter(self._filter)
        except Exception:
            logger.exception("Global hotkey teardown failed.")
        finally:
            self._registered = False
            self._filter = None

    def is_registered(self) -> bool:
        return self._registered

    def describe(self) -> str:
        parts = []
        if self._modifiers & self.MOD_CONTROL:
            parts.append("Ctrl")
        if self._modifiers & self.MOD_ALT:
            parts.append("Alt")
        if self._modifiers & self.MOD_SHIFT:
            parts.append("Shift")
        if self._modifiers & self.MOD_WIN:
            parts.append("Win")
        names = {self.VK_SPACE: "Space"}
        parts.append(names.get(self._vk, f"vk 0x{self._vk:02X}"))
        return " + ".join(parts)


_reduced_motion: bool | None = None


def reduced_motion() -> bool:
    """True when the OS accessibility settings ask for reduced motion.

    Cached — the setting doesn't change often enough to justify shelling out
    on every frame.
    """
    global _reduced_motion

    if _reduced_motion is not None:
        return _reduced_motion

    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(
                ["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
                capture_output=True, text=True, timeout=1,
            )
            _reduced_motion = result.stdout.strip() == "1"
        elif system == "Windows":
            # SPI_GETCLIENTAREAANIMATION via ctypes.windll.user32.
            # SystemParametersInfoW -- real, but unverified on the physical
            # machine, so it is not written blind here. Defaulting to full
            # motion (False) is the safe direction to be wrong in: it costs
            # a moment of unwanted animation, not a broken render.
            _reduced_motion = False
        else:
            _reduced_motion = False
    except Exception:
        _reduced_motion = False

    return _reduced_motion
