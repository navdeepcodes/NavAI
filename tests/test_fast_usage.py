"""Keeping track of today's free Fast mode allowance."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import _isolate  # noqa: F401,E402

from brain import fast_usage  # noqa: E402


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(fast_usage, "_path", lambda: tmp_path / "fast_usage.json")
    monkeypatch.setattr(fast_usage, "_state", None)
    yield
    fast_usage._state = None


def test_each_call_adds_what_cloudflare_says_it_cost():
    fast_usage.record({"prompt_tokens": 27, "completion_tokens": 5, "neurons": 0.38181817})
    fast_usage.record({"neurons": 99.6})
    assert abs(fast_usage.used() - 99.98181817) < 1e-6
    assert "Used today: 100 of 10,000 (1%)" in fast_usage.describe()


def test_a_response_with_no_cost_adds_nothing():
    for usage in (None, {}, {"neurons": 0}, {"neurons": "x"}, "nope"):
        fast_usage.record(usage)
    assert fast_usage.used() == 0.0


def test_the_total_survives_a_restart_and_starts_over_each_utc_day(monkeypatch):
    fast_usage.record({"neurons": 1234.0})
    fast_usage._state = None                       # a new run of Mike
    assert fast_usage.used() == 1234.0
    monkeypatch.setattr(fast_usage, "_today", lambda: "2099-01-01")
    assert fast_usage.used() == 0.0, "00:00 UTC: a fresh allowance"


def test_cloudflare_saying_it_is_gone_marks_the_day_used_up():
    fast_usage.record({"neurons": 300.0})
    fast_usage.mark_used_up()
    assert fast_usage.used() == fast_usage.DAILY_NEURONS
    assert "used up" in fast_usage.describe()
    assert fast_usage.warning() is None, "nothing to warn about once it's gone"


def test_the_warning_is_said_once_a_day_when_most_is_used():
    fast_usage.record({"neurons": 7000.0})
    assert fast_usage.warning() is None
    fast_usage.record({"neurons": 1200.0})
    said = fast_usage.warning()
    assert said and "82%" in said and "model on this computer" in said
    assert fast_usage.warning() is None


def test_the_provider_counts_a_streamed_answer_and_asks_for_its_cost():
    from brain.providers import workers_ai_provider as fast
    body = fast._Cloud("m")._payload([{"role": "user", "content": "hi"}], None, True)
    assert body["stream_options"] == {"include_usage": True}
    assert "stream_options" not in fast._Cloud("m")._payload([{"role": "user", "content": "hi"}], None, False)

    class Cloud:
        def last_usage(self):
            return {"neurons": 42.0}

    shell = fast.WorkersAIProvider.__new__(fast.WorkersAIProvider)
    shell._cloud, shell._notice = Cloud(), None
    shell._count_usage()
    assert fast_usage.used() == 42.0


def test_the_corner_ring_shows_only_with_fast_mode_and_tells_what_is_left(monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from brain.providers import workers_ai_provider as fast
    from ui.workspace.usage import UsageRing

    fast_usage.record({"neurons": 6200.0})
    monkeypatch.setattr(fast, "fast_mode_on", lambda: False)
    ring = UsageRing()
    holder = __import__("PySide6.QtWidgets", fromlist=["QWidget"]).QWidget()
    ring.setParent(holder)
    holder.show()
    ring.refresh()
    assert not ring.isVisible(), "no ring without Fast mode"

    monkeypatch.setattr(fast, "fast_mode_on", lambda: True)
    ring.refresh()
    assert ring.isVisible() and "38%" in ring.toolTip()
    ring._open()
    card = ring._card
    assert card.isVisible() and "Resets at" in card._resets.text() and "6,200 of 10,000" in card._used.text()
    assert abs(card._ring.used - 0.62) < 1e-6
    card.hide()
    holder.hide()
    app.processEvents()
