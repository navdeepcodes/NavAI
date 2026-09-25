"""Keeps the active mission true while you work — without the model.

Every few seconds this looks at the modification time of the mission's work
files (a stat, microseconds). Only when one changes — you saved in Word — does
it read the document and re-check the steps, off the GUI thread, and hand the
result back to the GUI thread. So the mission bar and the corner move as the
work moves, at no cost to the model and nothing at all while nothing changes.

Evaluation runs on a plain thread and comes back through a queued signal on
this QObject (which lives on the GUI thread), so the views are only ever
touched from the thread that owns them.
"""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from logs.logger import logger

POLL_MS = 3000


class MissionTracker(QObject):

    #: (mission or None, steps newly done, what changed) — on the GUI thread.
    changed = Signal(object, list, list)
    _evaluated = Signal(object, list, list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._evaluated.connect(self._deliver)
        self._busy = False
        self._again = False
        self._mtimes: dict[str, float | None] = {}
        self._mission_id: int | None = None
        self._signature = None
        self.current: dict | None = None

    def start(self) -> None:
        self._timer.start()
        self.refresh()

    def stop(self) -> None:
        self._timer.stop()

    def refresh(self) -> None:
        """Re-check now (after a turn, or when a mission starts or ends)."""
        if self._busy:
            self._again = True
            return
        self._busy = True
        threading.Thread(target=self._work, name="mission-check", daemon=True).start()

    def _work(self) -> None:
        try:
            from brain import mission_store as ms
            mission = ms.active()
            if mission is None:
                # Just finished? Show it finished for a moment rather than
                # having the bar vanish the instant the work is done.
                last = ms.get(self._mission_id) if self._mission_id else None
                if last is not None and last["status"] == "done":
                    self._evaluated.emit(last, [], [])
                    return
                self._evaluated.emit(None, [], [])
                return
            r = ms.evaluate(mission["id"])
            if ms.complete_if_done(mission["id"]):
                self._evaluated.emit(ms.get(mission["id"]), r["newly_done"], r["changes"])
                return
            self._evaluated.emit(r["mission"], r["newly_done"], r["changes"])
        except Exception:
            logger.exception("Mission check failed.")
            self._evaluated.emit(self.current, [], [])

    def _deliver(self, mission, newly_done: list, changes: list) -> None:
        self._busy = False
        if mission is not None and mission.get("status") == "done":
            # shown once as finished, then the bar settles away
            self.current = None
            self._mission_id = None
            self._mtimes = {}
            self._signature = None
            self.changed.emit(mission, [], [])
            self._rerun_if_asked()
            return
        self.current = mission
        self._mission_id = mission["id"] if mission else None
        self._mtimes = {f["path"]: _mtime(f["path"])
                        for f in (mission or {}).get("files", []) if f["role"] == "work"}
        signature = None if mission is None else (
            mission["id"], mission["goal"], mission["deadline"], mission["blocker"],
            tuple((s["title"], s["status"], s["evidence"]) for s in mission["steps"]))
        if signature != self._signature or newly_done:
            self._signature = signature
            self.changed.emit(mission, list(newly_done), list(changes))
        self._rerun_if_asked()

    def _rerun_if_asked(self) -> None:
        if self._again:
            self._again = False
            self.refresh()

    def _poll(self) -> None:
        if self._busy:
            return
        try:
            from brain import mission_store as ms
            row = ms.active()
        except Exception:
            return
        active_id = row["id"] if row else None
        if active_id != self._mission_id:
            self.refresh()
            return
        if any(_mtime(path) != seen for path, seen in self._mtimes.items()):
            self.refresh()


def _mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None
