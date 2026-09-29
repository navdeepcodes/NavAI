"""Bringing a window to the front, from the thread Mike's tools run on.

Measured in the packaged app: with Mike's own window in front, switching to
Notepad from the tool worker thread was refused by Windows twice, and "type
hello in notepad" failed. The worker joined the target's input queue, which
never makes it the foreground one.
"""
import platform
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="Windows foreground rules")


def _window(title):
    from PySide6.QtWidgets import QApplication, QWidget

    app = QApplication.instance() or QApplication([])
    w = QWidget()
    w.setWindowTitle(title)
    w.resize(400, 200)
    w.show()
    app.processEvents()
    return app, w


def _pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def test_a_worker_thread_brings_another_window_to_the_front():
    import win32gui
    from hostplatform.foreground import bring_to_front

    app, first = _window("Mike foreground test A")
    _, second = _window("Mike foreground test B")
    _pump(app, 0.3)
    assert bring_to_front(int(first.winId()))           # the "Mike" window, in front
    _pump(app, 0.3)

    result = {}
    worker = threading.Thread(target=lambda: result.update(ok=bring_to_front(int(second.winId()))))
    worker.start()
    while worker.is_alive():
        _pump(app, 0.05)
    assert result["ok"]
    assert win32gui.GetForegroundWindow() == int(second.winId())
    first.close()
    second.close()


def test_a_window_already_in_front_is_left_alone():
    from hostplatform.foreground import bring_to_front

    app, w = _window("Mike foreground test C")
    _pump(app, 0.3)
    assert bring_to_front(int(w.winId()))
    assert bring_to_front(int(w.winId()))
    w.close()
