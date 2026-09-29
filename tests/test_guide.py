"""While Mike works in other apps: his window steps aside, and the nib shows
where he's working.

The nib's flight and landing were checked on a real screen at 2x display
scaling (the nib's pixels 2px from the target); these cover the rules around
it: when the window steps aside, what the guide does with each request, and
that nothing here can hold an action up.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import _isolate  # noqa: F401,E402

from computer import attention  # noqa: E402


@pytest.fixture(autouse=True)
def no_listener():
    yield
    attention.set_listener(None)


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


# ── computer/attention.py ────────────────────────────────────

def test_with_nobody_listening_every_call_is_a_no_op():
    started = time.monotonic()
    attention.point("click", 10, 20, "Clicking")
    attention.window(SimpleNamespace(x=0, y=0, width=100, height=50), "Opening")
    assert not attention.active() and time.monotonic() - started < 0.05


def test_an_action_waits_for_the_nib_but_never_longer_than_the_cap(monkeypatch):
    seen = []
    attention.set_listener(lambda kind, x, y, label: seen.append((kind, x, y, label)) or 0.2)
    started = time.monotonic()
    attention.point("click", 10.7, 20, "Clicking Save")
    assert 0.18 < time.monotonic() - started < 0.6
    assert seen == [("click", 10, 20, "Clicking Save")]

    attention.set_listener(lambda *a: 30.0)
    monkeypatch.setattr(attention, "MAX_WAIT", 0.1)
    started = time.monotonic()
    attention.point("type", None, None, "Typing")
    assert time.monotonic() - started < 0.5, "a slow nib can't hold the action up"


def test_a_listener_that_fails_never_breaks_the_action():
    def boom(*a):
        raise RuntimeError("no")
    attention.set_listener(boom)
    attention.point("click", 1, 2, "x")          # must not raise
    attention.window(object(), "x")              # bounds it can't read: ignored


def test_a_window_is_pointed_at_along_its_title_bar():
    seen = []
    attention.set_listener(lambda kind, x, y, label: seen.append((kind, x, y)) or 0)
    attention.window(SimpleNamespace(x=100, y=200, width=800, height=600), "Opening")
    assert seen == [("window", 500, 218)]


# ── the labels ───────────────────────────────────────────────

def test_the_label_says_what_is_being_done():
    from computer.session import _click_label
    button = SimpleNamespace(label="Save")
    assert _click_label(button, "left", 1) == "Clicking Save"
    assert _click_label(button, "right", 1) == "Right-clicking Save"
    assert _click_label(button, "left", 2) == "Double-clicking Save"
    assert _click_label(None, "left", 1) == "Clicking"
    assert len(_click_label(SimpleNamespace(label="x" * 90), "left", 1)) <= len("Clicking ") + 28


# ── the guide ────────────────────────────────────────────────

def test_the_window_steps_aside_once_per_task_at_the_first_action():
    app = _app()
    from config import preferences
    from ui.workspace.guide import Guide
    preferences.set_value("guide_nib", False)          # nothing drawn on this desktop
    try:
        guide = Guide()
        stepped = []
        guide.outside_work.connect(lambda x, y: stepped.append((x, y)))

        guide.request("click", 5, 6, "Clicking")            # no task running
        _pump(app, 0.05)
        assert stepped == [], "only work done for a task counts"

        guide.begin_turn()
        worker = threading.Thread(target=lambda: guide.request("click", 5, 6, "Clicking"))
        worker.start()
        _pump(app, 0.3)
        worker.join(2)
        guide.request("type", None, None, "Typing")
        _pump(app, 0.05)
        assert stepped == [(5, 6)], "once, at the first action, from any thread"

        guide.begin_turn()                                  # the next task
        guide.request("scroll", 7, 8, "Scrolling")
        _pump(app, 0.05)
        assert stepped == [(5, 6), (7, 8)]
    finally:
        preferences.set_value("guide_nib", True)


def _window(**over):
    state = dict(minimised=False, visible=True, inside=False, went=[])
    state.update(over)
    return SimpleNamespace(
        isMinimized=lambda: state["minimised"], isVisible=lambda: state["visible"],
        _own_window_holds=lambda x, y: state["inside"],
        _go_corner=lambda: state["went"].append(1)), state


def test_the_app_steps_aside_only_when_the_work_is_outside_it():
    from config import preferences
    from ui.app import MikeWindow
    step = MikeWindow._collapse_for_task

    window, state = _window()
    step(window, 900, 400)
    assert state["went"] == [1], "work in another app: step aside"

    window, state = _window(inside=True)
    step(window, 100, 100)
    assert state["went"] == [], "a click inside Mike's own window isn't 'outside'"

    window, state = _window(minimised=True)
    step(window, 900, 400)
    assert state["went"] == [], "already out of the way"

    window, state = _window()
    step(window, -1, -1)
    assert state["went"] == [1], "no position known (typing): still outside work"

    preferences.set_value("guide_collapse", False)
    try:
        window, state = _window()
        step(window, 900, 400)
        assert state["went"] == [], "the student turned it off"
    finally:
        preferences.set_value("guide_collapse", True)
