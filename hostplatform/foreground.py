"""Bring a window to the front on Windows, and say whether it really came.

Windows only lets a thread change the foreground if its input queue is the
foreground one, or its process has the right some other way. On this machine
the foreground lock never times out, so a refusal is final. Mike's tools run on
a worker thread, whose queue is never the foreground one even while Mike's own
window is in front. Measured in the packaged app: with Mike frontmost,
SetForegroundWindow(Notepad) from the worker was refused twice, 40s apart, and
"type hello in notepad" failed. The old workaround joined the *target's* input
queue, which does not make the caller foreground.

So, each step checked before the next:
  1. join the input queue of the thread that owns the foreground window (and
     the target's), which puts this thread in the foreground queue -- the
     documented way;
  2. SwitchToThisWindow, the call Alt+Tab itself makes -- no keys pressed.

Two fallbacks were tried and removed, both measured doing harm:
  - tapping Alt (a key press Windows accepts as permission to switch) left
    Windows 11 Notepad in its Alt-shortcut mode: "hello from mike" arrived as
    "heellpo om mi", the letters taken as menu shortcuts -- 2 of 2 garbled in a
    side-by-side test, while steps 1 and 2 typed cleanly 4 of 4;
  - minimise-and-restore left Calculator minimised, and the next step reported
    it wasn't running at all.
"""
from __future__ import annotations

import time

from logs.logger import logger


def _is_front(user32, hwnd: int, wait: float) -> bool:
    deadline = time.monotonic() + wait
    while True:
        if user32.GetForegroundWindow() == hwnd:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def bring_to_front(hwnd: int) -> bool:
    import ctypes

    import win32api
    import win32con
    import win32gui
    import win32process

    user32 = ctypes.windll.user32
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    if _is_front(user32, hwnd, 0):
        return True

    me = win32api.GetCurrentThreadId()
    front = user32.GetForegroundWindow()
    front_thread = win32process.GetWindowThreadProcessId(front)[0] if front else 0
    target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]
    attached = [t for t in {front_thread, target_thread}
                if t and t != me and user32.AttachThreadInput(me, t, True)]
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        for t in attached:
            user32.AttachThreadInput(me, t, False)
    if _is_front(user32, hwnd, 0.4):
        return True

    user32.SwitchToThisWindow(hwnd, True)
    if _is_front(user32, hwnd, 0.6):
        logger.info("Brought a window to the front with SwitchToThisWindow after "
                    "SetForegroundWindow was refused.")
        return True
    logger.warning("Windows refused to bring the window to the front.")
    return False
