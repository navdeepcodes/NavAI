"""Mike's mark -- the nib, still, with a glow that says what he's doing.

The brand is a fountain-pen nib angled like a mouse pointer (ui/workspace/
nib.py). It used to act out each state -- doodling while thinking, tapping
while working, rocking while speaking -- which read as scribbling. Now it
holds still, like a logo should, and a soft glow at its tip breathes: slowly
at rest, a little quicker while Mike is busy. Waiting on you, an error, or
done show in its colour. The clock stops when hidden, so an idle Mike costs
nothing.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from ui.panel import style

_MOVING = {"listening", "thinking", "working", "responding", "speaking"}


class PresenceMark(QWidget):
    def __init__(self, diameter: int = 32, parent=None) -> None:
        super().__init__(parent)
        self._d = diameter
        self.setFixedSize(diameter, diameter)
        self._state = "idle"
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._retime()
        self.update()

    def _retime(self) -> None:
        if not self.isVisible():
            self._timer.stop()
            return
        if style.reduced_motion():
            self._timer.start(1000 // 30)
            QTimer.singleShot(400, self._timer.stop)
            return
        if self._state in _MOVING or self._state == "idle":
            self._timer.start(1000 // 30 if self._state in _MOVING else 1000 // 15)
        else:
            self._timer.start(1000 // 30)
            QTimer.singleShot(500, self._timer.stop)

    def showEvent(self, e):
        super().showEvent(e); self._retime()

    def hideEvent(self, e):
        super().hideEvent(e); self._timer.stop()

    def _tick(self) -> None:
        self._t += 1 / 30
        self.update()

    def _colour(self) -> QColor:
        if self._state == "needs_user":
            return QColor(style.WARN)
        if self._state == "error":
            return QColor(style.STOP)
        if self._state == "done":
            return QColor(style.GOOD)
        return style.qaccent()

    # ── painting ──────────────────────────────────────────
    def paintEvent(self, _e) -> None:
        from ui.workspace import nib as _nib

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        d = float(self._d)
        col = self._colour()
        size = d * 0.86
        still = style.reduced_motion()

        # The nib stays still in every state -- it's the logo, not a pen
        # scribbling. What Mike is doing shows only as a soft glow at the tip:
        # a slow breath at rest, a quicker one while he's busy.
        tip = QPointF(d * 0.30, d * 0.22)
        busy = self._state in _MOVING
        if self._state in ("idle", "done") or busy:
            speed = 3.2 if busy else 1.8
            breath = 0.5 + 0.5 * math.sin(self._t * speed) if not still else 0.8
            r = d * (0.06 + (0.035 if busy else 0.02) * breath)
            g = QRadialGradient(tip, r * 2.4)
            halo = QColor(col); halo.setAlpha(int((95 if busy else 70) * breath))
            g.setColorAt(0, halo)
            g.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
            p.setPen(Qt.NoPen); p.setBrush(g)
            p.drawEllipse(tip, r * 2.4, r * 2.4)

        _nib.paint(p, tip, size, col, col.darker(210), _nib.ANGLE)
