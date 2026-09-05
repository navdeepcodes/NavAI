"""Mike's presence indicator — a subtle animated dot that communicates state."""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer, QRectF, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QRadialGradient
from PySide6.QtWidgets import QWidget

from ui.theme import colors


class PresenceIndicator(QWidget):
    """Animated presence dot that reflects Mike's current state.

    States: idle, listening, transcribing, thinking, tool, speaking, done
    """

    SIZE = 48

    _COLORS = {
        "idle": QColor(colors.ACCENT),
        "listening": QColor("#4A90FF"),
        "transcribing": QColor("#4A90FF"),
        "thinking": QColor(colors.ACCENT),
        "tool": QColor(colors.ACCENT),
        "speaking": QColor("#4A90FF"),
        "done": QColor(colors.SUCCESS),
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._state = "idle"
        self._phase = 0.0
        self._glow = 0.3

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30fps
        self._timer.timeout.connect(self._tick)

        self._glow_anim = QPropertyAnimation(self, b"glow", self)
        self._glow_anim.setDuration(800)
        self._glow_anim.setEasingCurve(QEasingCurve.InOutSine)

    def _get_glow(self) -> float:
        return self._glow

    def _set_glow(self, v: float) -> None:
        self._glow = v
        self.update()

    glow = Property(float, _get_glow, _set_glow)

    def set_state(self, state: str) -> None:
        self._state = state

        self._glow_anim.stop()

        if state == "idle":
            self._timer.stop()
            self._glow = 0.3
        elif state == "listening":
            self._timer.start()
        elif state == "transcribing":
            self._timer.start()
        elif state == "thinking":
            self._timer.start()
        elif state == "tool":
            self._timer.start()
        elif state == "speaking":
            self._timer.start()
        elif state == "done":
            self._timer.stop()
            self._glow_anim.setStartValue(0.8)
            self._glow_anim.setEndValue(0.3)
            self._glow_anim.setDuration(1200)
            self._glow_anim.start()

        self.update()

    def _tick(self) -> None:
        self._phase += 0.05
        if self._phase > 2 * math.pi * 100:
            self._phase = 0
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cx = self.width() / 2
        cy = self.height() / 2
        base_color = self._COLORS.get(self._state, self._COLORS["idle"])

        if self._state == "idle":
            r = 5
            p.setPen(Qt.NoPen)
            c = QColor(base_color)
            c.setAlphaF(self._glow)
            grad = QRadialGradient(cx, cy, r * 2)
            grad.setColorAt(0, c)
            grad.setColorAt(0.5, c)
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(grad)
            p.drawEllipse(QRectF(cx - r * 2, cy - r * 2, r * 4, r * 4))
            p.setBrush(base_color)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        elif self._state == "listening":
            pulse = 0.5 + 0.5 * math.sin(self._phase * 2)
            r = 6 + pulse * 4
            c = QColor(base_color)
            c.setAlphaF(0.15 + pulse * 0.15)
            grad = QRadialGradient(cx, cy, r * 2.5)
            grad.setColorAt(0, c)
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(grad)
            p.drawEllipse(QRectF(cx - r * 2.5, cy - r * 2.5, r * 5, r * 5))
            p.setBrush(base_color)
            p.drawEllipse(QRectF(cx - 6, cy - 6, 12, 12))

        elif self._state in ("transcribing", "thinking"):
            speed = 3 if self._state == "transcribing" else 1.5
            alpha = 0.4 + 0.3 * math.sin(self._phase * speed)
            c = QColor(base_color)
            c.setAlphaF(alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(QRectF(cx - 6, cy - 6, 12, 12))

        elif self._state == "tool":
            rotation = self._phase * 2
            alpha = 0.5 + 0.3 * math.sin(self._phase * 3)
            c = QColor(base_color)
            c.setAlphaF(alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            r = 5
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
            orbit_r = 10
            dot_r = 2.5
            for i in range(3):
                angle = rotation + i * (2 * math.pi / 3)
                dx = cx + orbit_r * math.cos(angle)
                dy = cy + orbit_r * math.sin(angle)
                dc = QColor(base_color)
                dc.setAlphaF(0.4)
                p.setBrush(dc)
                p.drawEllipse(QRectF(dx - dot_r, dy - dot_r, dot_r * 2, dot_r * 2))

        elif self._state == "speaking":
            bars = 5
            bar_w = 3
            gap = 2
            total_w = bars * bar_w + (bars - 1) * gap
            sx = cx - total_w / 2
            for i in range(bars):
                phase_offset = i * 0.8
                h = 4 + 8 * abs(math.sin(self._phase * 2.5 + phase_offset))
                x = sx + i * (bar_w + gap)
                y = cy - h / 2
                c = QColor(base_color)
                c.setAlphaF(0.7)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(x, y, bar_w, h), 1.5, 1.5)

        elif self._state == "done":
            c = QColor(base_color)
            c.setAlphaF(self._glow)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(QRectF(cx - 6, cy - 6, 12, 12))

        p.end()
