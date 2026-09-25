"""Bring a window to the front on Windows, and say whether it really came.

Windows only lets a thread change the foreground if its input queue is the
foreground one, or its process has the right some other way (it received the
last input, the user pressed Alt, ...). On this machine the foreground lock
never times out, so a refusal is final. Mike's tools run on a worker thread,
whose queue is never the foreground one even while Mike's own window is in
front. Measured in the packaged app: with Mike frontmost, SetForegroundWindow
(Notepad) from the worker was refused twice, 40s apart, and "type hello in
notepad" failed. The old workaround joined the *target's* input queue, which
does not make the caller foreground.

So, each step checked before the next:
  1. join the input queue of the thread that owns the foreground window (and
     the target's), which puts this thread in the foreground queue -- the
     documented way;
  2. tap Alt twice: an Alt press is one of the things Windows accepts as the
     user's permission to switch windows, and the second tap closes the menu
     the first may have opened in the window being left;
  3. minimise and restore.
"""
from __future__ import annotations

import time


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

    for _ in range(2):
        user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
        user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)
    if _is_front(user32, hwnd, 0.4):
        return True

    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return _is_front(user32, hwnd, 1.0)
