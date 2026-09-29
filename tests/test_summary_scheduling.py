"""The background situation summary must never stall the student.

Measured on the target laptop: the summary is a ~25 s call to the same local
model, and it used to fire every 6 turns, immediately — so the next message
queued behind it and a 4 s answer took 29 s. It now runs only when history
nears the trim point, after an idle moment, and backs off if a new turn starts.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _core(monkeypatch, idle=0.3):
    from brain import mike_core
    monkeypatch.setattr(mike_core, "SUMMARY_IDLE_SECONDS", idle)
    core = mike_core.MikeCore(host="http://127.0.0.1:11434", summary_model="x")
    calls = []

    def fake_refresh(old, turns, project, epoch=None):
        calls.append(len(turns))
        core._summarizing = False

    monkeypatch.setattr(core, "_refresh_summary", fake_refresh)
    return core, calls, mike_core


def _fill(core, n):
    core.history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
                    for i in range(n)]


def test_short_conversations_never_pay_for_a_summary(monkeypatch):
    core, calls, _m = _core(monkeypatch)
    for _ in range(12):                       # used to fire at 6 and 12
        _fill(core, 20)
        core.note_turn_complete()
    time.sleep(0.6)
    assert calls == []


def test_near_the_trim_point_it_summarises_once_idle(monkeypatch):
    core, calls, m = _core(monkeypatch)
    _fill(core, m.MAX_HISTORY - m.SUMMARY_HEADROOM)
    core.note_turn_complete()
    assert calls == [], "must not start immediately, in front of the next turn"
    time.sleep(0.8)
    assert calls == [m.MAX_HISTORY - m.SUMMARY_HEADROOM]


def test_a_new_turn_during_the_wait_makes_it_back_off(monkeypatch):
    core, calls, m = _core(monkeypatch, idle=0.6)
    _fill(core, m.MAX_HISTORY - m.SUMMARY_HEADROOM)
    core.note_turn_complete()
    time.sleep(0.1)
    core.history.append({"role": "user", "content": "the student keeps talking"})
    time.sleep(0.9)
    assert calls == [], "a turn arrived, so the summary yields"
    core.note_turn_complete()                  # rescheduled after that turn
    time.sleep(0.9)
    assert len(calls) == 1


def test_at_the_hard_limit_it_does_not_wait(monkeypatch):
    core, calls, m = _core(monkeypatch, idle=30)
    _fill(core, m.MAX_HISTORY - 2)
    core.note_turn_complete()
    time.sleep(0.4)
    assert len(calls) == 1, "turns are about to be trimmed: summarise now"
