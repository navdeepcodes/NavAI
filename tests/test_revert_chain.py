"""Regression test for the revert-data-loss gap found during the trust-
boundary audit: revert_store.revert() used to overwrite/delete the file on
disk with no snapshot of what was there first. If the file had changed
again since Mike's original write — the user's own later edit, or a later
unrelated write — clicking "revert this" in History silently discarded
that state with zero warning and zero way back.

Proves two things against the real code (not a mock): a revert always
snapshots first, and HomeSurface._revert_change links that snapshot to a
real activity row, so a mistaken revert is itself always one more click
away from being undone.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — must run before any brain/config import


def test_revert_survives_an_intervening_edit():
    from brain import activity_store, revert_store
    from tools.filesystem import actions

    tmp = tempfile.mkdtemp()
    target = str(Path(tmp) / "notes.txt")

    Path(target).write_text("version A")
    row1 = activity_store.begin("Writing notes.txt")
    actions.write_file(target, "version B")
    revert_store.attach_to_activity(row1)

    # An edit lands on top of Mike's write — could be the user, could be a
    # later unrelated Mike action — before anyone clicks revert.
    Path(target).write_text("version C (written after Mike's change)")

    snap1 = revert_store.for_activity(row1)
    assert snap1 is not None

    result = revert_store.revert(snap1["id"])
    assert result["status"] == "success"
    assert Path(target).read_text() == "version A", "revert should restore the pre-write state"

    # The old code stopped here and "version C" was gone forever. Now the
    # revert itself must have captured "version C" first.
    orphan = revert_store._db().execute(
        "SELECT * FROM snapshots WHERE activity_id IS NULL ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert orphan is not None, "revert() must capture the pre-revert state"
    assert orphan["previous_content"] == "version C (written after Mike's change)"

    print("PASS: revert() snapshots the current state before overwriting it")


def test_home_revert_change_links_snapshot_to_a_findable_activity_row():
    from PySide6.QtWidgets import QApplication

    from brain import activity_store, revert_store
    from tools.filesystem import actions
    from ui.instrument.home import HomeSurface

    QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.mkdtemp()
    target = str(Path(tmp) / "config.json")

    Path(target).write_text('{"v": 1}')
    row1 = activity_store.begin("Writing config.json")
    actions.write_file(target, '{"v": 2}')
    revert_store.attach_to_activity(row1)

    page = HomeSurface({})
    snap1 = revert_store.for_activity(row1)
    page._revert_change(snap1["id"])

    assert Path(target).read_text() == '{"v": 1}'

    rows = activity_store.recent(limit=20)
    revert_row = next(r for r in rows if r["action"] == "Reverting a change")
    assert revert_row["succeeded"] == 1

    snap2 = revert_store.for_activity(revert_row["id"])
    assert snap2 is not None, "the revert's own before-state must be linked to its activity row"
    assert snap2["previous_content"] == '{"v": 2}'

    # And that revert is itself revertible, through the exact same UI path.
    page._revert_change(snap2["id"])
    assert Path(target).read_text() == '{"v": 2}', "reverting the revert must restore what it undid"

    print("PASS: HomeSurface._revert_change makes every revert itself revertible")


if __name__ == "__main__":
    test_revert_survives_an_intervening_edit()
    test_home_revert_change_links_snapshot_to_a_findable_activity_row()
    print("\nAll revert-chain regression tests passed.")
