"""The dial — Mike's identity at every depth.

A real gauge, not a decoration: the arc is an honest reading (mic level while
listening, a settle-in sweep while thinking or working) and the needle's
position is state, not animation for its own sake. A small flag rises on the
rim when — and only when — Mike has actually stopped and needs a decision.

One widget, three sizes: ~26px in the edge and composer, ~110px at the head
of Home. Same object throughout.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from ui.home import motion
from ui.instrument import tokens

_ANIMATED = {"listening", "thinking", "working", "responding"}
_FPS = 30


class Dial(QWidget):

    def __init__(self, diameter: int = 84, parent=None) -> None:
        super().__init__(parent)
        self._d = diameter
        self._state = "idle"
        self._t0 = time.monotonic()
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._timer = QTimer(self)
        self._timer.setInterval(1000 // _FPS)
        self._timer.timeout.connect(self.update)
        self._sync_timer()

    # ── State ────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._t0 = time.monotonic()
        self._sync_timer()
        self.update()

    def state(self) -> str:
        return self._state

    def _sync_timer(self) -> None:
        should = self._state in _ANIMATED and self.isVisible() and not motion.reduced_motion()
        if should and not self._timer.isActive():
            self._timer.start()
        elif not should and self._timer.isActive():
            self._timer.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    # ── Paint ────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        d = self._d
        cx, cy = d / 2.0, d / 2.0
        r_outer = d / 2.0 - 1.5
        r_face = r_outer * 0.80
        elapsed = time.monotonic() - self._t0
        reduced = motion.reduced_motion()

        tone = QColor(tokens.DIAL_TONE.get(self._state, tokens.AMBER))

        # Outer ring
        painter.setPen(QPen(QColor(tokens.HAIRLINE), max(1.0, d * 0.012)))
        painter.drawEllipse(QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2))

        # Machined metal face
        grad = QRadialGradient(cx - r_face * 0.3, cy - r_face * 0.35, r_face * 1.5)
        grad.setColorAt(0.0, QColor(tokens.METAL_HI))
        grad.setColorAt(0.7, QColor("#39332A"))
        grad.setColorAt(1.0, QColor(tokens.METAL_LO))
        painter.setPen(QPen(QColor("#0F0D0A"), max(1.0, d * 0.012)))
        painter.setBrush(grad)
        painter.drawEllipse(QRectF(cx - r_face, cy - r_face, r_face * 2, r_face * 2))

        # Arc — the honest reading
        sweep = self._arc_sweep(elapsed, reduced)
        if sweep > 0.001:
            pen = QPen(tone, max(1.6, d * 0.028))
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            arc_r = r_outer - pen.widthF() / 2
            arc_rect = QRectF(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)
            start_angle = 90 * 16
            span_angle = -int(360 * 16 * sweep)
            painter.drawArc(arc_rect, start_angle, span_angle)

        # Needle
        angle_deg = self._needle_angle(elapsed, reduced)
        alpha = self._needle_alpha(elapsed, reduced)
        needle_colour = QColor(tone)
        needle_colour.setAlphaF(alpha)
        needle_len = r_face * 0.62
        rad = math.radians(angle_deg - 90)
        nx = cx + needle_len * math.cos(rad)
        ny = cy + needle_len * math.sin(rad)
        pen = QPen(needle_colour, max(1.4, d * 0.024))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(cx), int(cy), int(nx), int(ny))

        painter.setPen(Qt.NoPen)
        painter.setBrush(tone)
        hub_r = max(1.6, d * 0.03)
        painter.drawEllipse(QRectF(cx - hub_r, cy - hub_r, hub_r * 2, hub_r * 2))

        # Flag — only when Mike has actually stopped for you
        if self._state == "needs_user":
            self._paint_flag(painter, d)

    def _arc_sweep(self, elapsed: float, reduced: bool) -> float:
        if self._state == "listening":
            if reduced:
                return 0.3
            return 0.18 + 0.22 * (0.5 + 0.5 * math.sin(elapsed * 2 * math.pi / 0.9))
        if self._state in ("working", "responding"):
            if reduced:
                return 0.4
            phase = (elapsed % 1.6) / 1.6
            return 0.15 + 0.55 * (0.5 - 0.5 * math.cos(phase * 2 * math.pi))
        if self._state == "error":
            return 0.28
        return 0.0

    def _needle_angle(self, elapsed: float, reduced: bool) -> float:
        if self._state == "idle":
            return -24
        if self._state == "listening":
            return 0
        if self._state == "thinking":
            if reduced:
                return 14
            return 14 * math.sin(elapsed * 2 * math.pi / 0.7)
        if self._state in ("working", "responding"):
            if reduced:
                return 40
            phase = (elapsed % 1.6) / 1.6
            return -30 + 130 * (0.5 - 0.5 * math.cos(phase * 2 * math.pi))
        if self._state == "needs_user":
            return 55
        if self._state == "done":
            return 40
        if self._state == "error":
            return -70
        return -24

    def _needle_alpha(self, elapsed: float, reduced: bool) -> float:
        if self._state == "idle" and not reduced:
            return 0.55 + 0.45 * (0.5 + 0.5 * math.sin(elapsed * 2 * math.pi / 3.6))
        return 1.0

    def _paint_flag(self, painter: QPainter, d: int) -> None:
        pole_x = d * 0.78
        pole_top = d * 0.10
        pole_bot = d * 0.42
        pen = QPen(QColor(tokens.FAINT), max(1.2, d * 0.02))
        painter.setPen(pen)
        painter.drawLine(int(pole_x), int(pole_top), int(pole_x), int(pole_bot))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tokens.RED))
        path = QPainterPath()
        fw, fh = d * 0.18, d * 0.11
        path.moveTo(pole_x, pole_top)
        path.lineTo(pole_x + fw, pole_top + fh / 2)
        path.lineTo(pole_x, pole_top + fh)
        path.closeSubpath()
        painter.drawPath(path)
