"""Mike's presence — a single small mark whose motion is its meaning.

Not an avatar, not a glowing orb. A thin ring with a core, drawn precisely,
where *how it moves* tells you what Mike is doing: breathing when at rest,
opening outward when listening, turning while thinking, sweeping while
working, pulsing while speaking, still and warm when it needs you. The colour
is Mike's accent, so a personalised Mike is personalised here first.

Motion is the state indicator because words and colour alone read as a status
badge; a living mark reads as presence. The animation is cheap and, crucially,
stops entirely when the mark is hidden or perfectly at rest, so an idle Mike
costs nothing.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from ui.panel import style

# Which states animate, and how fast to paint them. Idle breathes slowly;
# active states move enough to read as alive without becoming theatre.
_ACTIVE = {"listening", "thinking", "working", "responding", "speaking"}


class PresenceMark(QWidget):
    def __init__(self, diameter: int = 34, parent=None) -> None:
        super().__init__(parent)
        self._d = diameter
        self.setFixedSize(diameter, diameter)
        self._state = "idle"
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._sweep = 0.0

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
        if self._state in _ACTIVE:
            self._timer.start(33)          # ~30fps while doing something
        elif self._state in ("idle", "needs_user", "done", "error"):
            # idle still breathes, but slowly and cheaply
            self._timer.start(90) if self._state == "idle" else self._timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._retime()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self) -> None:
        self._phase += 0.06
        if self._state == "working":
            self._sweep = (self._sweep + 6) % 360
        self.update()

    # ── painting ─────────────────────────────────────────
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx = cy = self._d / 2
        centre = QPointF(cx, cy)
        r = self._d / 2 - 3
        acc = style.qaccent()

        breathe = 0.5 + 0.5 * math.sin(self._phase)

        if self._state == "listening":
            # concentric openings — sound arriving
            for i in range(3):
                t = (self._phase * 0.5 + i / 3.0) % 1.0
                rad = r * (0.35 + t * 0.9)
                a = int(120 * (1 - t))
                pen = QPen(QColor(acc.red(), acc.green(), acc.blue(), a))
                pen.setWidthF(1.4)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(centre, rad, rad)
            self._core(p, centre, r * 0.32, acc, 235)
            return

        if self._state in ("responding", "speaking"):
            # a soft pulse, like a voice
            pulse = 0.5 + 0.5 * math.sin(self._phase * 1.6)
            self._ring(p, centre, r, acc, 90)
            self._core(p, centre, r * (0.30 + 0.14 * pulse), acc, 210)
            return

        if self._state == "thinking":
            self._ring(p, centre, r, style.qaccent(), 55)
            self._arc(p, centre, r, self._phase * 60, 70, acc, 220, 1.8)
            self._core(p, centre, r * 0.22, acc, 180)
            return

        if self._state == "working":
            self._ring(p, centre, r, acc, 45)
            self._arc(p, centre, r, self._sweep, 110, acc, 230, 2.2)
            self._core(p, centre, r * 0.22, acc, 150)
            return

        if self._state == "needs_user":
            # still and attentive — a steady warm ring
            self._ring(p, centre, r, QColor(style.WARN), 200)
            self._core(p, centre, r * 0.30, QColor(style.WARN), 235)
            return

        if self._state == "error":
            self._ring(p, centre, r, QColor(style.STOP), 150)
            self._core(p, centre, r * 0.26, QColor(style.STOP), 200)
            return

        if self._state == "done":
            self._ring(p, centre, r, QColor(style.GOOD), 170)
            self._core(p, centre, r * 0.26, QColor(style.GOOD), 220)
            return

        # idle — a faint ring, a softly breathing core
        self._ring(p, centre, r, QColor(style.INK_FAINT), 160)
        self._core(p, centre, r * 0.26, acc, int(90 + 90 * breathe))

    def _ring(self, p, centre, r, colour, alpha):
        pen = QPen(QColor(colour.red(), colour.green(), colour.blue(), alpha))
        pen.setWidthF(1.5)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(centre, r, r)

    def _arc(self, p, centre, r, start_deg, span_deg, colour, alpha, width):
        pen = QPen(QColor(colour.red(), colour.green(), colour.blue(), alpha))
        pen.setWidthF(width)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        rect = (centre.x() - r, centre.y() - r, 2 * r, 2 * r)
        p.drawArc(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]),
                  int(-start_deg * 16), int(-span_deg * 16))

    def _core(self, p, centre, radius, colour, alpha):
        grad = QRadialGradient(centre, radius * 1.6)
        c = QColor(colour.red(), colour.green(), colour.blue())
        c.setAlpha(alpha)
        grad.setColorAt(0.0, c)
        edge = QColor(colour.red(), colour.green(), colour.blue(), 0)
        grad.setColorAt(1.0, edge)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawEllipse(centre, radius, radius)
