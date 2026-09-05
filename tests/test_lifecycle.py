"""Regression coverage for Mike's background-presence contract.

Mike's onboarding text tells the user, in his own voice: "I stay running in
the background." Before this, that was false — ui/app.py never called
setQuitOnLastWindowClosed(False) and had no tray presence, so clicking the
window's close button tore down the controller, unregistered the global
hotkey, and stopped the IDE bridge. The single most ordinary thing a person
can do to a window silently turned Mike off.

These tests pin the corrected contract from both directions, because only
testing one half would let the opposite bug in:

  closing the window  -> window hides, EVERY service stays alive
  explicitly quitting -> EVERY service is actually torn down, nothing orphaned

Exercises the real MikeWindow against real services (real Carbon hotkey
registration, real IDE bridge socket, real controller/worker threads) — not
mocks of the lifecycle. State is isolated per tests/_isolate.py.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — must run before any brain/config import


def _fresh_window():
    """A real MikeWindow with real services started, wake word disabled.

    Wake word is turned off through the ordinary preference rather than by
    patching, so this stays a real lifecycle: it keeps the test off the
    microphone (and off a permission prompt in CI) while leaving every other
    service — hotkey, IDE bridge, controller threads, Edge, tray — genuinely
    running. Wake-word teardown is covered separately in
    test_wake_word_survives_window_close.
    """
    from config import preferences

    preferences.set_value("wake_word_enabled", False)

    from ui.app import MikeWindow

    return MikeWindow()


def test_closing_the_window_does_not_quit_mike():
    from PySide6.QtWidgets import QApplication

    from ide import manager as ide_manager

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = _fresh_window()
    window.show()

    assert window.hotkey._registered, "hotkey should be live before the close"
    assert ide_manager._started, "IDE bridge should be live before the close"

    window.close()

    # The window goes away...
    assert not window.isVisible(), "closing the window should hide it"
    # ...but Mike does not.
    assert not window._torn_down, "closing the window must not tear Mike down"
    assert window.hotkey._registered, "global hotkey must survive a window close"
    assert ide_manager._started, "IDE bridge must survive a window close"
    assert window.tray.isVisible(), "tray presence must survive a window close"

    window._teardown()
    print("PASS: closing the window hides it and leaves every service running")


def test_quit_actually_tears_everything_down():
    from PySide6.QtWidgets import QApplication

    from ide import manager as ide_manager

    QApplication.instance() or QApplication(sys.argv)

    window = _fresh_window()
    window.show()

    # The real quit path, same one the tray's "Quit Mike" and Cmd+Q use.
    window._teardown()

    assert window._torn_down
    assert not window.hotkey._registered, "quit must unregister the global hotkey"
    assert not ide_manager._started, "quit must stop the IDE bridge"
    assert not window.tray.isVisible(), "quit must remove the tray presence"
    assert window.controller._worker is None, "no worker may be left running"
    assert window.controller._thread is None, "no thread may be left running"
    assert not window.controller._retired_threads, "no retired thread may be orphaned"

    print("PASS: an explicit quit tears down every service, orphaning nothing")


def test_close_event_refuses_normally_but_accepts_during_a_real_quit():
    """Regression for a bug this file's first version did NOT catch, because
    it called _teardown() directly and so never exercised the real quit path.

    Quitting asks every top-level window to close, and a window that ignores
    that request cancels the quit outright. With closeEvent ignoring
    unconditionally, "Quit Mike" called quit(), quit() asked the window to
    close, the window refused, and the whole termination was silently
    abandoned — aboutToQuit never fired, exec() never returned, and Mike
    could not be quit at all. Verified against the real app: it hung
    indefinitely before the fix and exits cleanly after.

    Both directions matter, so both are pinned here: refuse for an ordinary
    close (that's the whole background-presence feature) and accept during a
    genuine quit (or the app can never exit).
    """
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    window = _fresh_window()

    ordinary = QCloseEvent()
    window.closeEvent(ordinary)
    assert not ordinary.isAccepted(), "an ordinary close must be refused, so Mike keeps running"

    # What the tray's "Quit Mike" and Cmd+Q actually do first.
    window._quitting = True

    during_quit = QCloseEvent()
    window.closeEvent(during_quit)
    assert during_quit.isAccepted(), (
        "during a real quit the window must accept the close — refusing here "
        "cancels the quit and leaves Mike unquittable"
    )

    window._teardown()
    print("PASS: close is refused normally and accepted during a real quit")


def test_teardown_is_idempotent():
    """aboutToQuit and run()'s post-exec call can both fire; the second must
    be a harmless no-op rather than double-stopping live services."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    window = _fresh_window()
    window._teardown()
    window._teardown()  # must not raise
    window._teardown()

    assert window._torn_down
    print("PASS: teardown is idempotent")


def test_close_then_reopen_restores_a_working_window():
    """Closing is 'put it away', so reopening has to genuinely bring it back
    — including through the same path the tray's "Show Mike" item uses."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    window = _fresh_window()
    window.show()
    window.close()
    assert not window.isVisible()

    window._show_main_window()

    assert window.isVisible(), "Show Mike must bring the window back"
    assert not window._torn_down, "reopening must not have needed a restart"

    window._teardown()
    print("PASS: close then reopen restores a working window")


def test_global_invocation_still_works_after_the_window_is_closed():
    """The whole point of staying alive: summoning Mike from anywhere has to
    work when his window is gone, which is exactly when it matters most."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    window = _fresh_window()
    window.show()
    window.close()

    # This is what the Carbon hotkey callback invokes.
    window._summon()

    assert window.floating.isVisible(), "global invocation must work with the window closed"

    window.floating.dismiss()
    window._teardown()
    print("PASS: global invocation still works with the main window closed")


def test_edge_ambient_presence_wakes_when_the_window_closes():
    """The Edge strip is Mike's ambient 'still here' surface. It sleeps while
    the window is up and must wake when the window goes away — that transition
    is driven by hideEvent, which a close now actually triggers."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    window = _fresh_window()
    window.show()
    app = QApplication.instance()
    app.processEvents()

    assert not window.edge.isVisible(), "Edge should sleep while the window is up"

    window.close()
    app.processEvents()

    assert window.edge.isVisible(), "Edge must wake when the window closes"

    window._teardown()
    print("PASS: Edge ambient presence wakes when the window closes")


def test_wake_word_survives_window_close_and_stops_on_quit():
    """Covers the one service _fresh_window leaves off, on its own terms:
    started for real, asserted across a close, and asserted stopped by quit."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    window = _fresh_window()
    window.show()

    if not window.controller._wake.start():
        print("SKIP: wake word unavailable in this environment")
        window._teardown()
        return

    assert window.controller._wake.is_active

    window.close()
    assert window.controller._wake.is_active, "wake word must survive a window close"

    window._teardown()
    assert not window.controller._wake.is_active, "quit must stop the wake word"
    print("PASS: wake word survives a window close and stops on quit")


if __name__ == "__main__":
    test_closing_the_window_does_not_quit_mike()
    test_quit_actually_tears_everything_down()
    test_close_event_refuses_normally_but_accepts_during_a_real_quit()
    test_teardown_is_idempotent()
    test_close_then_reopen_restores_a_working_window()
    test_global_invocation_still_works_after_the_window_is_closed()
    test_edge_ambient_presence_wakes_when_the_window_closes()
    test_wake_word_survives_window_close_and_stops_on_quit()
    print("\nAll lifecycle regression tests passed.")
