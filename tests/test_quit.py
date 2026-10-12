"""Mike must be quittable the way every Mac app is, and still stay put when
his window is merely closed.

Found on a real Mac: Dock > Quit and AppleScript's `quit` both failed with
"User cancelled" and the app could not be closed by hand. The system's quit
arrives as a request for every window to close, and Mike's closeEvent (which
sends the window to the corner instead of quitting) refused it.

tests/test_lifecycle.py pins the other two halves (close hides, his own Quit
tears everything down); this pins the operating system's quit request.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


class _Window:
    """Just what MikeWindow.closeEvent touches."""

    def __init__(self):
        self._quitting = False
        self.went_to_corner = 0
        self.geometry_saved = 0

    def _go_corner(self):
        self.went_to_corner += 1

    def _save_geometry(self):
        self.geometry_saved += 1


class _CloseEvent:
    def __init__(self):
        self.accepted = None

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def _close(window):
    from ui.app import MikeWindow

    event = _CloseEvent()
    MikeWindow.closeEvent(window, event)
    return event


def test_closing_the_window_still_sends_mike_to_the_corner():
    window = _Window()
    event = _close(window)
    assert event.accepted is False and window.went_to_corner == 1


def test_a_system_quit_is_let_through_where_a_plain_close_is_not():
    """The bug, end to end: plain close refused; quit request -> accepted."""
    from PySide6.QtCore import QEvent

    from ui.system.lifecycle import QuitRequests

    _app()
    window = _Window()
    assert _close(window).accepted is False, "a plain close must not quit Mike"

    filt = QuitRequests(lambda: setattr(window, "_quitting", True))
    swallowed = filt.eventFilter(None, QEvent(QEvent.Quit))
    assert swallowed is False, "the filter must never swallow the quit itself"

    event = _close(window)
    assert event.accepted is True and window.geometry_saved == 1


def test_other_events_do_not_look_like_a_quit():
    from PySide6.QtCore import QEvent

    from ui.system.lifecycle import QuitRequests

    _app()
    window = _Window()
    filt = QuitRequests(lambda: setattr(window, "_quitting", True))
    for kind in (QEvent.Close, QEvent.Show, QEvent.Hide, QEvent.Timer):
        filt.eventFilter(None, QEvent(kind))
    assert window._quitting is False


def test_a_broken_callback_cannot_stop_the_quit():
    from PySide6.QtCore import QEvent

    from ui.system.lifecycle import QuitRequests

    _app()

    def boom():
        raise RuntimeError("nope")

    assert QuitRequests(boom).eventFilter(None, QEvent(QEvent.Quit)) is False


def test_the_filter_is_installed_on_the_application():
    """The fix is worthless if run() never installs it."""
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "ui" / "app.py").read_text(encoding="utf-8")
    assert "QuitRequests" in source and "installEventFilter" in source
