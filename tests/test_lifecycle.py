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



def _away(window) -> bool:
    """Put away: since Mike stays in the taskbar ("in the dock"), closing or
    minimising leaves the window minimised there rather than fully hidden."""
    return (not window.isVisible()) or window.isMinimized()


def _up(window) -> bool:
    return window.isVisible() and not window.isMinimized()


def case_closing_the_window_does_not_quit_mike():
    from PySide6.QtWidgets import QApplication

    from ide import manager as ide_manager

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = _fresh_window()
    window.show()

    # Whatever this platform's hotkey state genuinely is before the close —
    # registered on macOS, unregistered on Windows, which has no backend yet
    # (GlobalHotkey.register() fails softly by design, the same way a failed
    # Carbon call would). Either is legitimate; what this test actually
    # guards against is closing the window *changing* that state, not the
    # state itself.
    hotkey_was_registered = window.hotkey._registered
    assert ide_manager._started, "IDE bridge should be live before the close"

    window.close()

    # The window goes away...
    assert _away(window), "closing the window should put it away (to the taskbar)"
    # ...but Mike does not.
    assert not window._torn_down, "closing the window must not tear Mike down"
    assert window.hotkey._registered == hotkey_was_registered, (
        "closing the window must not change the hotkey's registration state"
    )
    assert ide_manager._started, "IDE bridge must survive a window close"
    assert window.tray.isVisible(), "tray presence must survive a window close"

    window._teardown()
    print("PASS: closing the window hides it and leaves every service running")


def case_quit_actually_tears_everything_down():
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


def case_close_event_refuses_normally_but_accepts_during_a_real_quit():
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


def case_teardown_is_idempotent():
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


def case_close_then_reopen_restores_a_working_window():
    """Closing is 'put it away', so reopening has to genuinely bring it back
    — including through the same path the tray's "Show Mike" item uses."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    window = _fresh_window()
    window.show()
    window.close()
    assert _away(window)

    window._show_full()

    assert _up(window), "Open Mike must bring the window back"
    assert not window._torn_down, "reopening must not have needed a restart"

    window._teardown()
    print("PASS: close then reopen restores a working window")


def case_global_invocation_still_works_after_the_window_is_closed():
    """The whole point of staying alive: summoning Mike from anywhere has to
    work when his window is gone, which is exactly when it matters most."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    window = _fresh_window()
    window.show()
    window.close()
    assert _away(window)

    # This is what the Carbon hotkey callback invokes. In the redesigned
    # interaction model the panel *is* the summoned presence, so the hotkey
    # brings the panel itself forward rather than a separate quick-line.
    window._summon()

    assert _up(window), "global invocation must bring Mike forward with the window closed"

    # And it toggles: pressing it again while Mike is up puts him away. The
    # dismiss fades out first, so it completes on the event loop — pump it.
    import time

    from PySide6.QtWidgets import QApplication

    window._summon()
    deadline = time.time() + 1.5
    while _up(window) and time.time() < deadline:
        QApplication.instance().processEvents()
        time.sleep(0.01)
    assert _away(window), "summoning again should put Mike away"

    window._teardown()
    print("PASS: global invocation still works with the main window closed")


def case_corner_presence_appears_when_the_window_closes():
    """CORNER MIKE is the ambient 'still here' companion (it replaced the old
    Edge strip). It stays away while the workspace is up, appears when the
    window is put away, and steps aside again when the window comes back."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)

    window = _fresh_window()
    window.show()
    app = QApplication.instance()
    app.processEvents()

    assert not window.corner.isVisible(), "the corner should stay away while the window is up"

    window.close()
    app.processEvents()

    assert window.corner.isVisible(), "the corner must appear when the window is put away"

    window._show_full()
    app.processEvents()
    assert not window.corner.isVisible(), "the corner steps aside when Mike is full again"

    window._teardown()
    print("PASS: corner presence appears when the window closes")


def case_wake_word_survives_window_close_and_stops_on_quit():
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


# ── each case runs in its own process ─────────────────────────
#
# Every case builds a full, real MikeWindow with its services running (tray,
# hotkey, IDE bridge, corner, model warm-up, speech prewarm). The app only ever
# has ONE such window per process. Run as eight windows in one interpreter,
# the suite hit a nondeterministic native access violation during teardown that
# could not be reproduced outside pytest, in standalone multi-window scripts, or
# in the real app (verified with 25 minimise/corner/restore/hotkey cycles and
# forced collections). Each case passes on its own, so each gets a fresh
# process — the same shape the product runs in.

CASES = [name for name in list(globals()) if name.startswith("case_")]

import subprocess  # noqa: E402
import tempfile  # noqa: E402

import pytest  # noqa: E402


@pytest.mark.parametrize("case", CASES)
def test_lifecycle(case):
    env = dict(os.environ)
    env["MIKE_DATA_DIR"] = tempfile.mkdtemp(prefix="mike-lifecycle-")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(
        [sys.executable, os.path.abspath(__file__), case],
        capture_output=True, text=True, timeout=240, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, (
        f"{case} failed (exit {result.returncode}): "
        + result.stdout[-3000:] + " " + result.stderr[-3000:])


if __name__ == "__main__":
    # `python tests/test_lifecycle.py <case>` runs one case (how pytest drives
    # them); with no argument, every case in turn.
    _cases = [a for a in sys.argv[1:]] or list(CASES)
    for _name in _cases:
        globals()[_name]()
