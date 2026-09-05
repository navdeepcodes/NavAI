"""Regression test for the dangling-tool_end bug found during the trust-
boundary audit: retiring a worker (Stop, or sending a new message) while a
tool is mid-execution used to blanket-disconnect tool_end, so the tool's
already-created activity row was stuck "in progress" forever and, for a
write/delete, its revert snapshot became permanently unreachable — the tool
genuinely ran and captured a before-state, but nothing ever linked it to a
row the UI could show.

Exercises the real UIController._retire_active_worker /
_finalize_retired_activity path against real activity_store and
revert_store state (isolated, per tests/_isolate.py) — not a mock of the
fix, the actual code.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — must run before any brain/config import


def test_tool_end_after_retirement_still_completes_activity_row():
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication

    from brain import activity_store, revert_store
    from brain.core_runtime import CoreRuntime
    from ui.controller.ui_controller import UIController
    from ui.instrument.home import HomeSurface

    app = QApplication.instance() or QApplication(sys.argv)

    class FakeWorker(QObject):
        token = Signal(str)
        tool_start = Signal(str)
        tool_end = Signal(str)
        finished = Signal()
        error = Signal(str)
        confirmation_needed = Signal(str)

        def cancel(self) -> None:
            pass

    runtime = CoreRuntime()
    page = HomeSurface({})
    controller = UIController(runtime, page)

    worker = FakeWorker()
    controller._worker = worker
    controller._thread = None

    # Simulate a tool that already started (activity row created, revert
    # snapshot captured for its write) before the user hits Stop / sends a
    # new message.
    controller._on_tool_start("Writing config.json")
    row_id = controller._activity_row
    assert row_id is not None, "tool_start must create an activity row"

    snap_id = revert_store.capture("/tmp/does-not-need-to-exist-for-this-test.json")
    assert snap_id is not None
    revert_store.attach_to_activity(row_id)
    linked = revert_store.for_activity(row_id)
    assert linked is not None and linked["id"] == snap_id

    row_before = activity_store.get(row_id)
    assert row_before is not None
    assert row_before["outcome"] == "", "row should still be open before retirement"

    # User hits Stop (or sends a new message) while the tool is still
    # running — this is the exact moment the old code lost the pending
    # tool_end.
    controller._retire_active_worker()
    assert controller._activity_row is None, "retirement must clear the live pointer"

    # The tool actually finishes a moment later, on the now-retired worker.
    worker.tool_end.emit("Successfully wrote to config.json")

    row_after = activity_store.get(row_id)
    assert row_after is not None, "the row vanished"
    assert row_after["outcome"] == "Successfully wrote to config.json", (
        f"activity row was never closed out: {row_after}"
    )
    assert row_after["succeeded"] == 1

    print("PASS: retired worker's dangling tool_end still completes its activity row")


def test_denied_confirmation_after_retirement_marks_row_failed_not_stuck():
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication

    from brain import activity_store
    from brain.core_runtime import CoreRuntime
    from ui.controller.ui_controller import UIController
    from ui.instrument.home import HomeSurface

    QApplication.instance() or QApplication(sys.argv)

    class FakeWorker(QObject):
        token = Signal(str)
        tool_start = Signal(str)
        tool_end = Signal(str)
        finished = Signal()
        error = Signal(str)
        confirmation_needed = Signal(str)

        def cancel(self) -> None:
            pass

    runtime = CoreRuntime()
    page = HomeSurface({})
    controller = UIController(runtime, page)

    worker = FakeWorker()
    controller._worker = worker
    controller._thread = None

    controller._on_tool_start("Deleting old_file.txt")
    row_id = controller._activity_row

    controller._retire_active_worker()
    worker.tool_end.emit("Cancelled by user.")

    row_after = activity_store.get(row_id)
    assert row_after is not None, "the row vanished"
    assert row_after["outcome"] == "Cancelled by user."
    assert row_after["succeeded"] == 0, "a denied/cancelled tool must not read as succeeded"

    print("PASS: denied confirmation on a retired worker still resolves its activity row")


if __name__ == "__main__":
    test_tool_end_after_retirement_still_completes_activity_row()
    test_denied_confirmation_after_retirement_marks_row_failed_not_stuck()
    print("\nAll activity-finalization regression tests passed.")


def test_a_row_is_findable_by_id_no_matter_how_much_happens_after_it():
    """The flake this file suffered, pinned.

    Both tests above used to locate their row by scanning
    activity_store.recent(limit=50). That reads as equivalent to a lookup and
    is not: anything inserting rows afterwards pushes the row out of the
    window, and the scan then fails on a row that is present and correct.
    It failed roughly one run in four under MIKE_RUN_APP_E2E=1, where real
    windows and their worker threads are still writing activity.

    Reproduced deterministically here by doing what the suite does by
    accident — recording a lot of activity after the row of interest.
    """
    from brain import activity_store

    row_id = activity_store.begin("the action under test")
    assert row_id is not None

    for i in range(120):
        activity_store.complete(activity_store.begin(f"noise {i}"), "done")

    assert activity_store.get(row_id) is not None, (
        "the row became unfindable once later activity buried it"
    )
    assert activity_store.get(row_id)["action"] == "the action under test"

    # And the scan that used to be relied on genuinely cannot see it, which
    # is the point: the old lookup was wrong, not merely unlucky.
    window = activity_store.recent(limit=50)
    assert not any(r["id"] == row_id for r in window), (
        "this test no longer reproduces the condition it was written for"
    )

    activity_store.complete(row_id, "finished after all the noise")
    assert activity_store.get(row_id)["outcome"] == "finished after all the noise"


def test_recent_orders_deterministically_when_timestamps_collide():
    """started_at is a float and ties are rare, but an ordering that is only
    usually stable shows up as rows swapping places for no visible reason."""
    from brain import activity_store

    activity_store.clear()
    ids = [activity_store.begin(f"same instant {i}") for i in range(8)]

    # Force the collision the real world produces occasionally.
    activity_store._db().execute("UPDATE activity SET started_at = 1000.0")
    activity_store._db().commit()

    first = [r["id"] for r in activity_store.recent(limit=20)]
    for _ in range(5):
        assert [r["id"] for r in activity_store.recent(limit=20)] == first

    assert first == sorted(ids, reverse=True), "ties must fall back to insertion order"


def test_get_is_honest_about_a_row_that_does_not_exist():
    from brain import activity_store

    assert activity_store.get(9_999_999) is None
    assert activity_store.get(None) is None
