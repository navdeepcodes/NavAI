"""What Mike is doing on your computer — live, honest, then out of the way.

When Mike works (reads a file, opens an app, clicks through a window, writes
something), each step appears as a row with a mark that tells the truth about
it: a turning arc while it runs, a tick when it worked, a cross when it
didn't, a dash when you stopped it. A running step shows how long it has been
going, because a local model driving a real desktop can take real seconds per
step, and a counter that keeps moving is the difference between "slow" and
"stuck".

When the turn ends the card settles: a run of steps that all worked folds
into one line ("Done · 4 steps · 21s") you can open again, so the answer —
not the plumbing — is what you read. A failure stays open, so you see exactly
which step didn't work.

It speaks the same small contract as the old ledger (add_row / set_status /
set_text), so the controller drives it unchanged.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from ui.panel import style
from ui.workspace.icons import draw


def _fmt(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60:02d}s"


class _Mark:
    """Paint a step's status mark in a 16px box."""

    @staticmethod
    def paint(p: QPainter, r: QRectF, status: str, phase: float) -> None:
        if status == "running":
            track = QColor(style.INK)
            track.setAlpha(28)
            pen = QPen(track)
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(r.adjusted(1.5, 1.5, -1.5, -1.5))
            arc = QPen(style.qaccent())
            arc.setWidthF(2.0)
            arc.setCapStyle(Qt.RoundCap)
            p.setPen(arc)
            start = int(-phase * 360 * 16)
            p.drawArc(r.adjusted(1.5, 1.5, -1.5, -1.5), start, -100 * 16)
        elif status == "done":
            col = QColor(style.GOOD)
            tile = QColor(col)
            tile.setAlpha(46)
            p.setPen(Qt.NoPen)
            p.setBrush(tile)
            p.drawEllipse(r)
            draw(p, "check", r.adjusted(2.5, 2.5, -2.5, -2.5), col, 1.8)
        elif status == "failed":
            col = QColor(style.STOP)
            tile = QColor(col)
            tile.setAlpha(46)
            p.setPen(Qt.NoPen)
            p.setBrush(tile)
            p.drawEllipse(r)
            draw(p, "close", r.adjusted(3, 3, -3, -3), col, 1.8)
        elif status == "waiting":
            col = QColor(style.WARN)
            tile = QColor(col)
            tile.setAlpha(46)
            p.setPen(Qt.NoPen)
            p.setBrush(tile)
            p.drawEllipse(r)
            p.setBrush(col)
            c = r.center()
            p.drawRoundedRect(QRectF(c.x() - 3.5, c.y() - 3.5, 2.6, 7), 1, 1)
            p.drawRoundedRect(QRectF(c.x() + 0.9, c.y() - 3.5, 2.6, 7), 1, 1)
        else:  # stopped
            col = QColor(style.INK_MUTE)
            pen = QPen(col)
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(r.adjusted(1.5, 1.5, -1.5, -1.5))
            c = r.center()
            p.drawLine(QPointF(c.x() - 3, c.y()), QPointF(c.x() + 3, c.y()))


class _StepRow(QWidget):
    H = 30

    def __init__(self, card: "StepsCard", index: int, parent=None) -> None:
        super().__init__(parent)
        self._card = card
        self._index = index
        self.setFixedHeight(self.H)

    def paintEvent(self, _e) -> None:
        step = self._card._steps[self._index]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        waiting = step["status"] == "running" and self._card._waiting
        _Mark.paint(p, QRectF(2, (h - 16) / 2, 16, 16),
                    "waiting" if waiting else step["status"], self._card._phase)

        # how long it took (or has been taking): shown while running past a
        # beat, and afterwards only for steps slow enough to be worth noting
        took = step["end"] - step["start"] if step["end"] else time.monotonic() - step["start"]
        right = ""
        if waiting:
            right = "needs your OK"
        elif step["status"] == "running" and took >= 2:
            right = _fmt(took)
        elif step["status"] in ("done", "failed") and took >= 4:
            right = _fmt(took)
        rw = 0
        if right:
            p.setFont(style.font(style.CAPTION))
            p.setPen(QColor(style.INK_MUTE))
            rw = p.fontMetrics().horizontalAdvance(right) + 4
            p.drawText(QRectF(w - rw, 0, rw, h), Qt.AlignVCenter | Qt.AlignRight, right)

        running = step["status"] == "running"
        p.setFont(style.font(style.BODY))
        p.setPen(QColor(style.INK if running else style.INK_SOFT))
        avail = int(w - 30 - rw - 10)
        text = p.fontMetrics().elidedText(step["text"], Qt.ElideMiddle, avail)
        p.drawText(QRectF(30, 0, avail, h), Qt.AlignVCenter | Qt.AlignLeft, text)


class _ThinkingRow(QWidget):
    """Between steps: Mike deciding what to do next. Shown inside the card
    (rather than a separate line appearing and vanishing under it) so the
    layout holds still while he works."""
    H = 30

    def __init__(self, card: "StepsCard", parent=None) -> None:
        super().__init__(parent)
        self._card = card
        self.setFixedHeight(self.H)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        h = self.height()
        _Mark.paint(p, QRectF(2, (h - 16) / 2, 16, 16), "running", self._card._phase)
        p.setFont(style.font(style.BODY))
        p.setPen(QColor(style.INK_MUTE))
        p.drawText(QRectF(30, 0, self.width() - 30, h), Qt.AlignVCenter | Qt.AlignLeft,
                   "Working out the next step…")


class _Header(QWidget):
    clicked = Signal()
    H = 30

    def __init__(self, card: "StepsCard", parent=None) -> None:
        super().__init__(parent)
        self._card = card
        self.setFixedHeight(self.H)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        c = self._card
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        outcome = c.outcome()
        mark = {"working": "running", "done": "done", "failed": "failed",
                "stopped": "stopped"}[outcome]
        n = len(c._steps)
        steps = f"{n} step{'s' if n != 1 else ''}"
        if outcome == "working" and c._waiting:
            mark = "waiting"
        title = "Waiting for your OK" if (outcome == "working" and c._waiting) else {
            "working": "Working on it",
            "done": f"Done · {steps}",
            "failed": "Couldn't finish",
            "stopped": "Stopped",
        }[outcome]
        _Mark.paint(p, QRectF(2, (h - 16) / 2, 16, 16), mark, c._phase)
        p.setFont(style.font(style.BODY, QFont.Weight.DemiBold))
        p.setPen(QColor(style.STOP if outcome == "failed" else style.INK))
        fm = p.fontMetrics()
        p.drawText(QRectF(30, 0, w - 120, h), Qt.AlignVCenter | Qt.AlignLeft, title)
        tx = 30 + fm.horizontalAdvance(title)

        elapsed = c.elapsed()
        meta = _fmt(elapsed) if elapsed >= 1 else ""
        if meta:
            p.setFont(style.font(style.CAPTION))
            p.setPen(QColor(style.INK_MUTE))
            p.drawText(QRectF(tx + 10, 0, 120, h), Qt.AlignVCenter | Qt.AlignLeft, meta)

        if c.collapsible():
            draw(p, "chevron-right" if c._collapsed else "chevron-down",
                 QRectF(w - 20, (h - 16) / 2, 16, 16), QColor(style.INK_MUTE), 1.6)


class StepsCard(QFrame):
    """The live list of what Mike is doing, one row per step."""

    _FRAME_MS = 33

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("steps")
        self._steps: list[dict] = []
        self._rows: list[_StepRow] = []
        self._settled: str | None = None
        self._collapsed = False
        self._phase = 0.0
        self._start = time.monotonic()
        self._end: float | None = None
        self._waiting = False

        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(14, 8, 14, 8)
        self._col.setSpacing(2)
        self._header = _Header(self)
        self._header.clicked.connect(self._toggle)
        self._header.hide()
        self._col.addWidget(self._header)
        self._thinking = _ThinkingRow(self)
        self._thinking.hide()

        self._timer = QTimer(self)
        self._timer.setInterval(self._FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._restyle()

    def _restyle(self) -> None:
        self.setStyleSheet(
            f"QFrame#steps{{background:{style.GROUND_RAISED};"
            f"border:1px solid {style.HAIRLINE};border-radius:12px;}}")

    # ── the contract the controller drives (via _ActionHandle) ──
    def add_row(self, text: str) -> int:
        if self._settled:
            # a later step in the same turn: the card is live again
            self._settled = None
            self._end = None
            self._collapsed = False
            for row in self._rows:
                row.show()
        self.set_thinking(False)
        self._steps.append({"text": text, "status": "running",
                            "start": time.monotonic(), "end": 0.0})
        row = _StepRow(self, len(self._steps) - 1)
        row.setToolTip(text)
        self._rows.append(row)
        self._col.addWidget(row)
        self._header.setVisible(len(self._steps) > 1)
        self._sync()
        return len(self._steps) - 1

    def set_status(self, index: int, status: str) -> None:
        if 0 <= index < len(self._steps):
            step = self._steps[index]
            step["status"] = status
            if status != "running" and not step["end"]:
                step["end"] = time.monotonic()
            self._sync()

    def set_text(self, index: int, text: str) -> None:
        if 0 <= index < len(self._steps):
            self._steps[index]["text"] = text
            self._rows[index].setToolTip(text)
            self._rows[index].update()

    def set_thinking(self, on: bool) -> None:
        """Mike is between steps, deciding what to do next."""
        on = bool(on) and not self._settled
        if on:
            self._col.removeWidget(self._thinking)
            self._col.addWidget(self._thinking)     # always the last row
        self._thinking.setVisible(on)
        self._sync()

    def set_waiting(self, on: bool) -> None:
        """Mike has asked for your OK and is paused until you answer."""
        self._waiting = bool(on)
        self._sync()

    # ── the end of the turn ──
    def settle(self, how: str = "done") -> None:
        """The turn is over. `how` is "done" or "stopped" (the user stopped it).

        A step still marked running can't still be running once the turn has
        ended — it was interrupted — so it is marked stopped rather than left
        turning forever.
        """
        now = time.monotonic()
        self._waiting = False
        self._thinking.hide()
        for step in self._steps:
            if step["status"] == "running":
                step["status"] = "stopped"
                step["end"] = now
        self._settled = how
        self._end = now
        if self.collapsible() and self.outcome() == "done":
            self._collapsed = True
            for row in self._rows:
                row.hide()
        self._sync()

    def outcome(self) -> str:
        statuses = [s["status"] for s in self._steps]
        if not self._settled:
            # until the turn is over, Mike is still at it — even between
            # steps, when every row so far is ticked
            return "working"
        if "failed" in statuses:
            return "failed"
        if "stopped" in statuses or self._settled == "stopped":
            return "stopped"
        if self._settled or statuses and all(s == "done" for s in statuses):
            return "done"
        return "working"

    def collapsible(self) -> bool:
        return bool(self._settled) and len(self._steps) > 1

    def elapsed(self) -> float:
        return (self._end or time.monotonic()) - self._start

    def is_running(self) -> bool:
        return any(s["status"] == "running" for s in self._steps)

    # ── internals ──
    def _toggle(self) -> None:
        if not self.collapsible():
            return
        self._collapsed = not self._collapsed
        for row in self._rows:
            row.setVisible(not self._collapsed)
        self._header.update()

    def _sync(self) -> None:
        live = (self.is_running() or self._thinking.isVisible()) and not self._waiting
        if live and not self._settled:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
        self._header.setCursor(Qt.PointingHandCursor if self.collapsible() else Qt.ArrowCursor)
        self._header.update()
        for row in self._rows:
            row.update()

    def _tick(self) -> None:
        if not style.reduced_motion():
            self._phase = (self._phase + self._FRAME_MS / 1000.0 * 0.9) % 1.0
        self._header.update()
        if self._thinking.isVisible():
            self._thinking.update()
        for row, step in zip(self._rows, self._steps):
            if step["status"] == "running":
                row.update()

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self._timer.stop()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._sync()
