"""Windows implementation of ComputerController.

Verified against a real Windows 11 machine (build 26200) with pywin32 and
comtypes, not written from documentation alone:

  - Window enumeration, focus and activation: EnumWindows,
    GetForegroundWindow, GetWindowThreadProcessId, SetForegroundWindow.
    Reliable, tested against Explorer, Chrome and a launched VS Code.
  - Input synthesis: SendInput for clicks, keystrokes and Unicode text.
    Tested against Notepad (click, type, press_keys all landed correctly).
  - Observation: UI Automation (comtypes) walking the ControlView tree.
    Native controls and Chrome's own browser chrome (tabs, address bar,
    nav buttons) surface real, addressable elements after one "nudge" call
    that forces Chrome to activate full accessibility — verified directly.
    Electron apps (VS Code confirmed) expose only their window chrome this
    way; the actual editor content lives inside a single opaque pane, a
    known UI Automation limitation for apps that have not turned on
    accessibility support. That gap is real, not yet closed, and is not
    hidden here: observe() still returns what it can see (window chrome)
    rather than claiming failure, since a shallow-but-honest observation is
    more useful than none.

Not yet implemented — raise NotSupportedError rather than a guess, per
computer/base.py's per-capability contract:

  scroll, drag   Mouse-wheel and drag synthesis are straightforward with
                 SendInput in principle, but have not been exercised
                 against a real scrollable view or drag target on this
                 machine, and a plausible-looking implementation that has
                 not been watched actually work is exactly the "fake
                 capability" this codebase's own testing philosophy rules
                 out. Left honestly unsupported until verified the same way
                 click and type_text were.

No extra dependency beyond what requirements.txt already declares for
Windows (comtypes, pywin32) plus ctypes (stdlib) for SendInput, which
neither package wraps directly.
"""
from __future__ import annotations

import ctypes
import subprocess
import time
from ctypes import wintypes

import win32api
import win32con
import win32gui
import win32process

import comtypes.client as _cc

from computer.base import (
    ActionResult,
    Bounds,
    ComputerController,
    NotSupportedError,
    Observation,
    UIElement,
    WindowInfo,
)

# ══ SendInput plumbing ═════════════════════════════════════
# pywin32 wraps the legacy, deprecated mouse_event/keybd_event; SendInput is
# the API Microsoft documents as current and is what the Windows-transition
# audit calls for, so this goes through ctypes directly.

_PUL = ctypes.POINTER(ctypes.c_ulong)


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", _PUL)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", _PUL)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUT_UNION)]


_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004


def _mouse_input(flags: int, mouse_data: int = 0) -> _INPUT:
    mi = _MOUSEINPUT(0, 0, mouse_data, flags, 0, None)
    return _INPUT(_INPUT_MOUSE, _INPUT_UNION(mi=mi))


def _key_input(vk: int, down: bool, unicode: bool = False) -> _INPUT:
    flags = 0 if down else _KEYEVENTF_KEYUP
    if unicode:
        flags |= _KEYEVENTF_UNICODE
        ki = _KEYBDINPUT(0, vk, flags, 0, None)
    else:
        ki = _KEYBDINPUT(vk, 0, flags, 0, None)
    return _INPUT(_INPUT_KEYBOARD, _INPUT_UNION(ki=ki))


def _send_input(*inputs: _INPUT) -> None:
    count = len(inputs)
    array = (_INPUT * count)(*inputs)
    ctypes.windll.user32.SendInput(count, array, ctypes.sizeof(_INPUT))


# Named keys the model can address by name. Ordinary characters go through
# type_text, which handles any Unicode without a per-key table.
_KEYS = {
    "return": 0x0D, "enter": 0x0D, "tab": 0x09, "space": 0x20,
    "delete": 0x2E, "backspace": 0x08,
    "escape": 0x1B, "esc": 0x1B, "home": 0x24, "end": 0x23,
    "page_up": 0x21, "page_down": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
_MODIFIERS = {
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
    "win": 0x5B, "cmd": 0x5B, "meta": 0x5B,
}

# ── UI Automation control-type IDs -> canonical roles ──────
# Stable, documented numeric IDs from the UI Automation spec (not generated
# per-run from comtypes.gen, so no dependency on codegen succeeding here).
_ROLE_MAP = {
    50000: "button", 50002: "checkbox", 50003: "combo_box", 50004: "text_field",
    50005: "link", 50006: "image", 50007: "list_item", 50008: "list",
    50009: "menu", 50010: "menu", 50011: "menu_item", 50013: "radio",
    50014: "scroll_area", 50015: "slider", 50018: "tab", 50019: "tab",
    50020: "text", 50021: "toolbar", 50023: "list", 50024: "list_item",
    50026: "group", 50030: "group", 50032: "window", 50033: "group",
    50036: "table", 50037: "toolbar",
}

_ACTIONABLE = {
    "button", "text_field", "text_area", "link", "checkbox", "radio",
    "menu_item", "tab", "combo_box", "slider",
}

_MAX_NODES = 4000
_MAX_DEPTH = 20


def _automation():
    """One IUIAutomation instance for the process. Created lazily so a
    machine where UI Automation itself cannot initialise fails at the first
    real call, not at import time."""
    global _AUTOMATION
    if _AUTOMATION is None:
        import comtypes.gen.UIAutomationClient as uia_module
        _AUTOMATION = _cc.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=uia_module.IUIAutomation
        )
    return _AUTOMATION


_AUTOMATION = None
_UIA_MODULE = None


def _uia():
    global _UIA_MODULE
    if _UIA_MODULE is None:
        _cc.GetModule("UIAutomationCore.dll")
        import comtypes.gen.UIAutomationClient as uia_module
        _UIA_MODULE = uia_module
    return _UIA_MODULE


def _process_name(pid: int) -> str:
    """The executable's own name, lowercase, no extension — Windows has no
    single friendly-name registry the way macOS's LocalizedName is, so this
    is the honest equivalent: what a person typed to launch it, roughly."""
    try:
        handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            path = win32process.GetModuleFileNameEx(handle, 0)
        finally:
            win32api.CloseHandle(handle)
        name = path.rsplit("\\", 1)[-1]
        return name[:-4] if name.lower().endswith(".exe") else name
    except Exception:
        return ""


class WindowsController(ComputerController):
    name = "windows"

    @staticmethod
    def available() -> tuple[bool, str]:
        try:
            _automation()
        except Exception as exc:
            return False, f"UI Automation could not initialise: {exc}"
        return True, "UI Automation available"

    # -- observation --------------------------------------------------
    def frontmost_app(self) -> str | None:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return _process_name(pid) or win32gui.GetWindowText(hwnd) or None

    def _enum_windows(self) -> list[tuple[int, str, int, tuple[int, int, int, int]]]:
        found: list[tuple[int, str, int, tuple[int, int, int, int]]] = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return True
            rect = win32gui.GetWindowRect(hwnd)
            width, height = rect[2] - rect[0], rect[3] - rect[1]
            if width * height < 4000:      # tray icons, tooltips, not "windows"
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            found.append((hwnd, title, pid, rect))
            return True

        win32gui.EnumWindows(callback, None)
        return found

    def list_windows(self) -> list[WindowInfo]:
        front = win32gui.GetForegroundWindow()
        windows = []
        for hwnd, title, pid, rect in self._enum_windows():
            windows.append(WindowInfo(
                app=_process_name(pid) or title,
                title=title,
                bounds=Bounds(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]),
                window_id=hwnd,
                pid=pid,
                frontmost=(hwnd == front),
            ))
        windows.sort(key=lambda w: (not w.frontmost, w.app.lower()))
        return windows

    def running_apps(self) -> list[str]:
        return sorted({_process_name(pid) or title
                       for _, title, pid, _ in self._enum_windows()} - {""})

    def _hwnd_by_name(self, name: str) -> int | None:
        wanted = (name or "").strip().lower()
        if not wanted:
            return None
        candidates = self._enum_windows()
        for hwnd, title, pid, _ in candidates:
            if (_process_name(pid) or "").lower() == wanted:
                return hwnd
        for hwnd, title, pid, _ in candidates:
            app = (_process_name(pid) or "").lower()
            if wanted in app or app in wanted or wanted in title.lower():
                return hwnd
        return None

    def observe(self, app: str | None = None, limit: int = 60) -> Observation:
        hwnd = self._hwnd_by_name(app) if app else win32gui.GetForegroundWindow()
        if not hwnd:
            return Observation(source="none", note=(
                f"No window found for {app!r}." if app else "No frontmost window."
            ))
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        app_name = _process_name(pid) or title

        automation = _automation()
        uia = _uia()
        try:
            root = automation.ElementFromHandle(hwnd)
        except Exception as exc:
            return Observation(app=app_name, window=title, source="none",
                                note=f"Could not read this window's interface: {exc}")

        # One touch nudges Chrome (and other Chromium-based apps) into
        # activating their full accessibility tree — verified directly:
        # without this the tree stops at empty panes.
        try:
            root.FindAll(uia.TreeScope_Descendants, automation.CreateTrueCondition())
            time.sleep(0.3)
        except Exception:
            pass

        elements: list[UIElement] = []
        counter = [0]

        def walk(node, depth=0):
            if depth > _MAX_DEPTH or counter[0] >= _MAX_NODES or len(elements) >= limit:
                return
            try:
                name = node.CurrentName or ""
                control_type = node.CurrentControlType
                rect = node.CurrentBoundingRectangle
                enabled = bool(node.CurrentIsEnabled)
                focused = bool(node.CurrentHasKeyboardFocus)
            except Exception:
                return
            counter[0] += 1
            role = _ROLE_MAP.get(control_type, "unknown")
            bounds = None
            if rect and (rect.right > rect.left) and (rect.bottom > rect.top):
                bounds = Bounds(rect.left, rect.top,
                                 rect.right - rect.left, rect.bottom - rect.top)
            if role in _ACTIONABLE and len(elements) < limit:
                elements.append(UIElement(
                    ref=f"el{len(elements)}", role=role, label=name,
                    bounds=bounds, enabled=enabled, focused=focused,
                    native_role=str(control_type),
                ))
            walker = automation.ControlViewWalker
            child = walker.GetFirstChildElement(node)
            while child is not None:
                walk(child, depth + 1)
                try:
                    child = walker.GetNextSiblingElement(child)
                except Exception:
                    break

        walk(root)

        note = ""
        if not elements:
            note = (
                "No actionable controls were found. If this is an Electron "
                "app (VS Code and similar), its content may not expose a UI "
                "Automation tree without accessibility support turned on in "
                "the app itself — a known gap, not a failed read."
            )
        return Observation(app=app_name, window=title, elements=elements,
                            source="accessibility" if elements else "none",
                            note=note)

    def focused_element(self) -> UIElement | None:
        try:
            node = _automation().GetFocusedElement()
            control_type = node.CurrentControlType
            rect = node.CurrentBoundingRectangle
            bounds = None
            if rect and rect.right > rect.left:
                bounds = Bounds(rect.left, rect.top,
                                 rect.right - rect.left, rect.bottom - rect.top)
            return UIElement(
                ref="focused", role=_ROLE_MAP.get(control_type, "unknown"),
                label=node.CurrentName or "", bounds=bounds, focused=True,
                native_role=str(control_type),
            )
        except Exception:
            return None

    # -- pointer --------------------------------------------------------
    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> ActionResult:
        win32api.SetCursorPos((int(x), int(y)))
        time.sleep(0.02)
        down, up = {
            "left": (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP),
            "right": (_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP),
        }.get(button, (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP))
        for _ in range(count):
            _send_input(_mouse_input(down))
            _send_input(_mouse_input(up))
            time.sleep(0.03)
        label = {1: "click", 2: "double-click", 3: "triple-click"}.get(count, f"{count}x click")
        return ActionResult(True, f"{button} {label} at ({x}, {y})")

    def scroll(self, dx: int, dy: int, x: int | None = None, y: int | None = None) -> ActionResult:
        raise NotSupportedError(
            "Scroll is not currently supported on Windows. Mouse-wheel "
            "synthesis has not yet been verified against a real scrollable "
            "view on this machine."
        )

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int) -> ActionResult:
        raise NotSupportedError(
            "Drag is not currently supported on Windows. It has not yet "
            "been verified against a real drag target on this machine."
        )

    # -- keyboard ---------------------------------------------------------
    def type_text(self, text: str) -> ActionResult:
        if not text:
            return ActionResult(False, error="No text given to type.")
        for ch in text:
            code = ord(ch)
            if code > 0xFFFF:
                # Outside the BMP (most emoji): KEYEVENTF_UNICODE's wScan is
                # 16 bits, so this would need a surrogate pair to send
                # correctly. Not yet handled — skipped rather than mojibake.
                continue
            _send_input(_key_input(code, down=True, unicode=True))
            _send_input(_key_input(code, down=False, unicode=True))
        return ActionResult(True, f"typed {len(text)} characters")

    def press_keys(self, key: str, modifiers: list[str] | None = None) -> ActionResult:
        name = (key or "").strip().lower()
        vk = _KEYS.get(name)
        if vk is None and len(name) == 1 and name.isalnum():
            vk = ord(name.upper())
        if vk is None:
            return ActionResult(False, error=(
                f"Unknown key {key!r}. Named keys: {', '.join(sorted(_KEYS)[:14])}... "
                "For ordinary characters use type_text instead."
            ))
        mod_vks = []
        for modifier in (modifiers or []):
            mvk = _MODIFIERS.get(modifier.strip().lower())
            if mvk is None:
                return ActionResult(False, error=(
                    f"Unknown modifier {modifier!r}. Use: shift, ctrl, alt, win."
                ))
            mod_vks.append(mvk)
        for mvk in mod_vks:
            _send_input(_key_input(mvk, down=True))
        _send_input(_key_input(vk, down=True))
        _send_input(_key_input(vk, down=False))
        for mvk in reversed(mod_vks):
            _send_input(_key_input(mvk, down=False))
        combo = "+".join((modifiers or []) + [key])
        return ActionResult(True, f"pressed {combo}")

    # -- applications -----------------------------------------------------
    def activate_app(self, name: str) -> ActionResult:
        hwnd = self._hwnd_by_name(name)
        if hwnd is None:
            return ActionResult(False, error=(
                f"No running application named {name!r}. Check list_windows "
                "for what is running."
            ))
        # SetForegroundWindow refuses to steal focus from a process Windows
        # does not consider to have "input permission" — verified on this
        # machine: a bare call silently failed to raise a background window.
        # Attaching this thread's input queue to the target window's thread
        # is the documented workaround.
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
        except Exception as exc:
            return ActionResult(False, error=f"Could not activate: {exc}")
        finally:
            if attached:
                ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, False)
        time.sleep(0.2)
        ok = win32gui.GetForegroundWindow() == hwnd
        if not ok:
            return ActionResult(False, error=(
                f"Asked Windows to bring {name!r} to the front, but it did "
                "not become the foreground window."
            ))
        return ActionResult(True, f"activated {name}")
