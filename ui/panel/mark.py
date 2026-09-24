"""Mike's mark — the nib. One pen, six behaviours.

The brand is a fountain-pen nib angled exactly like a mouse pointer: the thing
that writes and the thing that acts, in one silhouette (ui/workspace/nib.py).
Every state is that same nib doing something a hand does with a pen, never a
different drawing:

    resting     at rest on the page; a drop of ink at the tip breathes
    listening   lifted and poised, ready to take down what you say
    thinking    the tip turns small loops, like a pen doodling while you think
    working     taps in a steady rhythm, getting through the steps
    speaking    rocks gently with the voice
    needs you   still and upright, in the warning colour — your turn

So it always reads as the same pen — at rest, attentive, busy or waiting —
rather than six unrelated animations. It stops its clock when hidden or at
rest, so an idle Mike costs nothing.
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
        # eased so a change of state is a settle, not a jump
        self._lift = 0.0          # 0 on the page ‥ 1 lifted
        self._tilt = 0.0          # degrees away from the pointer angle

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

    # ── the animation model ───────────────────────────────
    def _targets(self) -> tuple[float, float]:
        s = self._state
        if s == "listening":
            return 1.0, -6.0
        if s == "needs_user":
            return 0.6, 14.0
        if s in ("responding", "speaking"):
            return 0.3, 5.0 * math.sin(self._t * 3.2)
        return 0.0, 0.0

    def _tick(self) -> None:
        self._t += 1 / 30
        lift, tilt = self._targets()
        self._lift += (lift - self._lift) * 0.2
        self._tilt += (tilt - self._tilt) * 0.25
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

        # where the tip is: the rest point, plus what the state is doing
        rest = QPointF(d * 0.30, d * 0.22)
        ox = oy = 0.0
        if not still:
            if self._state == "thinking":
                # small figure-of-eight doodle
                ox = d * 0.05 * math.sin(self._t * 3.1)
                oy = d * 0.035 * math.sin(self._t * 6.2)
            elif self._state == "working":
                tap = max(0.0, math.sin(self._t * 7.0))
                oy = -d * 0.06 * tap
        oy -= d * 0.07 * self._lift
        tip = QPointF(rest.x() + ox, rest.y() + oy)

        # the drop of ink at the tip — breathes at rest, full while working
        if self._state in ("idle", "working", "thinking", "done") and self._lift < 0.5:
            breath = 0.5 + 0.5 * math.sin(self._t * 1.8) if not still else 0.8
            r = d * (0.06 + 0.02 * breath)
            g = QRadialGradient(tip, r * 2.2)
            halo = QColor(col); halo.setAlpha(int(70 * breath))
            g.setColorAt(0, halo)
            g.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
            p.setPen(Qt.NoPen); p.setBrush(g)
            p.drawEllipse(tip, r * 2.2, r * 2.2)

        _nib.paint(p, tip, size, col, col.darker(210), _nib.ANGLE + self._tilt)
