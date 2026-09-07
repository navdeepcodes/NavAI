"""Mike's mark — the brand. One entity, six behaviours.

The silhouette is a small aperture: three short blades set around a luminous
core, the way a lens iris is built. It is deliberately not a plain ring —
three blades read as *focus*, as an intelligence turning its attention toward
you, and they stay recognisable from 24px in a header to 120px on a splash.

Every state is the same three blades and the same core doing something
different, never a different drawing:

    resting     blades still, wide open; the core breathes
    listening   blades open outward, receiving; core brightens
    thinking    blades rotate slowly, searching
    working     blades sweep in a steady cycle, making progress
    speaking    core pulses to the voice; blades hold, alert
    needs you   blades close in tight and warm; full attention on you

So it always looks like the same creature — awake, curious, busy, or waiting —
rather than six unrelated animations. Cheap to run and it stops dead when
hidden or fully at rest, so an idle Mike costs nothing.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from ui.panel import style

_MOVING = {"listening", "thinking", "working", "responding", "speaking"}

# The three blades, evenly spaced. Everything else is a transform of these.
_BASE_ANGLES = (90.0, 210.0, 330.0)


class PresenceMark(QWidget):
    def __init__(self, diameter: int = 32, parent=None) -> None:
        super().__init__(parent)
        self._d = diameter
        self.setFixedSize(diameter, diameter)
        self._state = "idle"
        self._t = 0.0                 # continuous animation clock
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        # eased state parameters, smoothed toward targets each frame so a
        # change of state is a settle, not a jump
        self._open = 1.0              # blade radius factor (0 tight ‥ 1 open)
        self._spin = 0.0              # blade rotation, degrees
        self._glow = 0.5              # core brightness 0‥1

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
        if self._state in _MOVING or self._state == "idle":
            self._timer.start(1000 // 30 if self._state in _MOVING else 1000 // 20)
        else:
            # needs_user / done / error settle once, then hold — but keep a
            # couple of frames so the easing lands cleanly.
            self._timer.start(1000 // 30)
            QTimer.singleShot(500, self._timer.stop)

    def showEvent(self, e):
        super().showEvent(e); self._retime()

    def hideEvent(self, e):
        super().hideEvent(e); self._timer.stop()

    # ── the animation model ───────────────────────────────
    def _targets(self):
        """Where the three parameters want to be for the current state."""
        s = self._state
        if s == "listening":
            return 1.28, self._spin, 0.9
        if s == "thinking":
            return 1.0, self._spin, 0.7
        if s == "working":
            return 1.05, self._spin, 0.65
        if s in ("responding", "speaking"):
            return 1.0, self._spin, 0.5 + 0.5 * (0.5 + 0.5 * math.sin(self._t * 5.0))
        if s == "needs_user":
            return 0.66, 0.0, 0.95
        if s in ("done", "error"):
            return 1.0, 0.0, 0.85
        # idle
        return 1.0, 0.0, 0.42 + 0.32 * (0.5 + 0.5 * math.sin(self._t * 1.6))

    def _tick(self) -> None:
        self._t += (1 / 30) if self._state in _MOVING else (1 / 20)
        if self._state == "thinking":
            self._spin = (self._spin + 1.7) % 360
        elif self._state == "working":
            self._spin = (self._spin + 4.0) % 360
        open_t, spin_t, glow_t = self._targets()
        # critically damped-ish easing toward targets
        self._open += (open_t - self._open) * 0.22
        self._glow += (glow_t - self._glow) * 0.30
        self.update()

    # ── painting ──────────────────────────────────────────
    def _colour(self) -> QColor:
        if self._state == "needs_user":
            return QColor(style.WARN)
        if self._state == "error":
            return QColor(style.STOP)
        if self._state == "done":
            return QColor(style.GOOD)
        return style.qaccent()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        d = self._d
        cx = cy = d / 2
        centre = QPointF(cx, cy)
        acc = self._colour()

        # geometry scales with size, so the mark is right at any diameter
        blade_r = (d * 0.30) * self._open
        blade_len = d * 0.30            # arc span expressed as a length
        stroke = max(1.2, d * 0.052)
        span_deg = 74.0
        # blades widen a touch when listening (receiving), tighten when needed
        if self._state == "listening":
            span_deg = 92.0
        elif self._state == "needs_user":
            span_deg = 58.0

        # the three blades — the identity, alone; no backing ring to dilute it
        blade = QColor(acc)
        blade.setAlpha(240 if self._state in _MOVING or self._state == "needs_user" else 205)
        pen = QPen(blade); pen.setWidthF(stroke); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        rect = QRectF(cx - blade_r, cy - blade_r, 2 * blade_r, 2 * blade_r)
        for base in _BASE_ANGLES:
            start = base + self._spin - span_deg / 2
            p.drawArc(rect, int(-start * 16), int(-span_deg * 16))

        # the core — the mind. A crisp solid dot, not a soft glow: a small
        # filled disc with only a hair of halo, so it reads as a precise point
        # of light, never a blob. Brightness carries breath (idle) and voice
        # (speaking); size holds steady so the point stays a point.
        glow = max(0.0, min(1.0, self._glow))
        core_r = d * 0.088
        halo = QRadialGradient(centre, core_r * 2.4)
        hc = QColor(acc); hc.setAlpha(int(60 * glow))
        halo.setColorAt(0.0, hc)
        halo.setColorAt(1.0, QColor(acc.red(), acc.green(), acc.blue(), 0))
        p.setPen(Qt.NoPen); p.setBrush(halo)
        p.drawEllipse(centre, core_r * 2.4, core_r * 2.4)
        solid = QColor(acc); solid.setAlpha(int(150 + 105 * glow))
        p.setBrush(solid)
        p.drawEllipse(centre, core_r, core_r)
