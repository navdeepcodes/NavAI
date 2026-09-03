"""Mike's visual presence.

Deliberately not a reactor core: the centre is dark and the light lives on the
rim, so it reads as an aperture opening onto something rather than a power
source. Arcs are asymmetric fragments at uneven radii drifting at different
speeds — never closed concentric rings, never gauge ticks.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from ui.home import motion


class PresenceCore(QWidget):

    # Arc fragments: (radius fraction, span°, drift speed, weight, start°)
    # Uneven radii, spans and start angles on purpose — evenly spaced rings
    # read as a gauge, and shared start angles read as lopsided rather than
    # deliberately asymmetric.
    _ARCS = (
        (0.96, 52, 0.14, 1.0, 18),
        (0.88, 96, 0.19, 2.0, 205),
        (0.88, 34, -0.11, 1.3, 96),
        (0.79, 22, 0.27, 1.0, 320),
        (0.70, 134, -0.23, 1.8, 42),
        (0.70, 28, 0.33, 1.1, 250),
        (0.62, 66, 0.40, 1.2, 145),
        (0.55, 44, -0.52, 1.0, 300),
    )

    def __init__(self, parent=None, size: int = 200) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._state = "idle"
        self._phase = 0.0
        self._energy = 0.0        # 0..1, how "awake" the presence looks
        self._energy_target = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._apply_state_motion()

    # ── State ────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        if state == self._state:
            return

        self._state = state
        self._apply_state_motion()
        self.update()

    def _apply_state_motion(self) -> None:
        targets = {
            "idle": 0.22,
            "listening": 0.85,
            "thinking": 0.6,
            "working": 0.7,
            "needs_user": 0.5,
            "responding": 0.65,
            "error": 0.35,
            "done": 0.3,
        }
        self._energy_target = targets.get(self._state, 0.25)

        if motion.reduced_motion():
            self._energy = self._energy_target
            self._timer.stop()
            return

        interval = (
            motion.IDLE_INTERVAL
            if self._state in ("idle", "needs_user", "done")
            else motion.ACTIVE_INTERVAL
        )
        self._timer.setInterval(interval)

        if self.isVisible():
            self._timer.start()

    # Stop burning frames when we're off screen.
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not motion.reduced_motion():
            self._timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self) -> None:
        self._phase += 0.016 if self._state == "idle" else 0.04
        if self._phase > math.tau * 1000:
            self._phase = 0.0

        self._energy += (self._energy_target - self._energy) * 0.08
        self.update()

    # ── Palette ──────────────────────────────────────────────

    def _hue(self) -> QColor:
        if self._state == "needs_user":
            return QColor(229, 168, 59)
        if self._state == "error":
            return QColor(229, 106, 90)
        if self._state == "done":
            return QColor(62, 207, 142)
        if self._state in ("listening", "working"):
            return QColor(79, 216, 232)
        return QColor(91, 140, 255)

    # ── Painting ─────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        half = min(cx, cy)
        hue = self._hue()
        energy = self._energy

        breathe = 1.0
        if not motion.reduced_motion():
            if self._state == "idle":
                breathe = 1.0 + 0.012 * math.sin(self._phase * 1.2)
            elif self._state == "listening":
                breathe = 1.0 + 0.045 * math.sin(self._phase * 3.4)
            elif self._state == "thinking":
                breathe = 1.0 - 0.03 * abs(math.sin(self._phase * 1.8))
            elif self._state == "responding":
                breathe = 1.0 + 0.025 * math.sin(self._phase * 2.2)
            elif self._state == "error":
                breathe = 1.0 + 0.01 * math.sin(self._phase * 9.0)

        radius = half * 0.86 * breathe

        self._paint_bloom(p, cx, cy, half, hue, energy)
        self._paint_arcs(p, cx, cy, radius, hue, energy)
        self._paint_aperture(p, cx, cy, radius * 0.52, hue, energy)

        p.end()

    def _paint_bloom(self, p, cx, cy, half, hue, energy) -> None:
        """Atmospheric glow. Carries most of the depth, none of the detail."""

        grad = QRadialGradient(QPointF(cx, cy), half)
        inner = QColor(hue)
        inner.setAlphaF(min(0.30, 0.05 + energy * 0.26))
        mid = QColor(hue)
        mid.setAlphaF(min(0.12, 0.02 + energy * 0.11))

        grad.setColorAt(0.0, inner)
        grad.setColorAt(0.45, mid)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QRectF(cx - half, cy - half, half * 2, half * 2))

    def _paint_arcs(self, p, cx, cy, radius, hue, energy) -> None:
        p.setBrush(Qt.NoBrush)

        for frac, span, speed, weight, origin in self._ARCS:
            r = radius * frac

            # Working state pushes the outer fragments around noticeably
            # faster, so progress reads as directional movement.
            drift = speed * (2.4 if self._state == "working" else 1.0)
            start = (origin + self._phase * drift * 57.3) % 360.0

            colour = QColor(hue)
            colour.setAlphaF(min(0.85, 0.18 + energy * 0.62))

            pen = QPen(colour)
            pen.setWidthF(weight)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)

            rect = QRectF(cx - r, cy - r, r * 2, r * 2)
            p.drawArc(rect, int(start * 16), int(span * 16))

    def _paint_aperture(self, p, cx, cy, r, hue, energy) -> None:
        """Dark centre, luminous rim — the part that isn't a reactor."""

        # Interior: darker than the page so it reads as depth, not a light.
        interior = QRadialGradient(QPointF(cx, cy), r)
        core = QColor(6, 7, 10)
        core.setAlphaF(0.96)
        edge = QColor(hue)
        edge.setAlphaF(0.10 + energy * 0.14)
        interior.setColorAt(0.0, core)
        interior.setColorAt(0.72, core)
        interior.setColorAt(1.0, edge)

        p.setPen(Qt.NoPen)
        p.setBrush(interior)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # Rim, brightest on one side so the form has a light direction.
        rim = QColor(hue)
        rim.setAlphaF(min(0.95, 0.30 + energy * 0.6))
        pen = QPen(rim)
        pen.setWidthF(1.4)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        sweep = 296
        offset = 214 if self._state != "working" else int((self._phase * 90) % 360)
        p.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), offset * 16, sweep * 16)
