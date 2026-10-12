"""The model download starts early, runs once, and tells the truth.

A new user's first message used to start a multi-GB download and then sit on
it. It now begins when Mike opens (while the person takes the tour), and the
two things that care -- the startup banner and a first message sent before it
ends -- must share ONE download rather than start two.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

from brain import model_download
from brain.providers.base import BrainError


class _Provider:
    """A provider whose model arrives in a few steps."""

    def __init__(self, steps=(10, 55, 100), fail=False, crash=False, pause=0.02):
        self.pulls = 0
        self._steps, self._fail, self._crash, self._pause = steps, fail, crash, pause

    def pull_model(self):
        self.pulls += 1
        if self._crash:
            raise RuntimeError("disk is full")
        for percent in self._steps:
            time.sleep(self._pause)
            yield f"Downloading Mike's language model - {percent}%"
        if self._fail:
            yield BrainError(kind="model_missing", message="The connection dropped.")


def _fresh(monkeypatch):
    monkeypatch.setattr(model_download, "POLL_SECONDS", 0.01)
    return model_download.ModelDownload()


def _wait_until(predicate, seconds=3.0):
    end = time.time() + seconds
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_starting_twice_downloads_once(monkeypatch):
    d, p = _fresh(monkeypatch), _Provider()
    assert d.start(p) is True
    assert d.start(p) is False, "a second start must join, not repeat"
    assert _wait_until(lambda: d.state == "done")
    assert p.pulls == 1 and d.percent == 100


def test_progress_is_reported_as_a_percentage(monkeypatch):
    d, p = _fresh(monkeypatch), _Provider(steps=(10, 55, 100), pause=0.08)
    d.start(p)
    assert _wait_until(lambda: d.percent == 55)
    assert d.active() and "55%" in d.snapshot()["detail"]


def test_a_message_sent_mid_download_follows_it_instead_of_starting_another(monkeypatch):
    d, p = _fresh(monkeypatch), _Provider(pause=0.05)
    d.start(p)                                  # began when Mike opened
    updates = list(d.follow(p))                 # the first message arrives
    assert p.pulls == 1, "a second download was started"
    assert updates and all("Downloading" in u for u in updates)
    assert d.state == "done"


def test_a_failure_is_the_last_thing_following_yields_and_can_be_retried(monkeypatch):
    d = _fresh(monkeypatch)
    broken = _Provider(fail=True)
    updates = list(d.follow(broken))
    assert isinstance(updates[-1], BrainError) and d.state == "failed"

    good = _Provider()
    assert d.start(good) is True, "a failed download must be retryable"
    assert _wait_until(lambda: d.state == "done") and good.pulls == 1


def test_a_provider_that_crashes_does_not_leave_it_stuck_downloading(monkeypatch):
    d = _fresh(monkeypatch)
    d.start(_Provider(crash=True))
    assert _wait_until(lambda: d.state == "failed")
    assert "disk is full" in d.error.message
    assert not d.active()


def test_once_the_model_has_arrived_nothing_is_started_or_awaited(monkeypatch):
    d, p = _fresh(monkeypatch), _Provider()
    d.start(p)
    assert _wait_until(lambda: d.state == "done")
    assert d.start(p) is False and p.pulls == 1
    list(d.follow(p))                             # returns promptly, no new pull
    assert p.pulls == 1


def test_a_provider_with_nothing_to_pull_is_left_alone(monkeypatch):
    d = _fresh(monkeypatch)
    assert d.start(object()) is False and d.state == "idle"


def test_stopping_the_wait_leaves_the_download_running(monkeypatch):
    d, p = _fresh(monkeypatch), _Provider(steps=(5, 20, 60, 100), pause=0.1)
    waiting = d.follow(p)
    next(waiting)                                 # the user sees the first progress...
    waiting.close()                               # ...and presses Stop
    assert d.active() or d.state == "done"
    assert _wait_until(lambda: d.state == "done"), "the download must carry on"


def test_the_startup_check_reports_progress_and_nothing_else_downloads(monkeypatch):
    from ui.workspace.health import BrainHealth

    monkeypatch.setattr(model_download.download, "state", "downloading")
    monkeypatch.setattr(model_download.download, "percent", 42)
    health = BrainHealth._probe()
    assert health["state"] == "downloading"
    assert "42%" in health["detail"] and health["can_start"] is False
