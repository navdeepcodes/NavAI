"""The voice trace — the nib drawing a voice as it happens.

Like the pen of a chart recorder: paper runs right to left, and the nib at
the right edge draws what it hears. Silence is a steady, flat line; speech
swings it, in step with the real loudness of the sound (voice.levels), so you
can see yourself being heard — and see when you've stopped.

    listen   your microphone, in ink, drawn by the nib
    read     the paper stops and the pen lifts; a light passes along what you
             said while it's being transcribed
    speak    Mike's own voice, in his accent ink, as it actually plays

The ink is the same broad-nib ink as the handwriting: fuller on the steep
strokes, finer on the flat, landing glossy and drying as it scrolls away.
With Reduce motion on, the trace is a still line and the pen rests.
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.panel import style
from ui.workspace import nib as _nib


class VoiceTrace(QWidget):

    PX = 2.0            # paper travel per frame, px (≈120 px/s)
    FRAME_MS = 16

    def __init__(self, compact: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._compact = compact
        self.setFixedHeight(26 if compact else 48)
        self.setMinimumWidth(120)
        self._mode = "off"
        self._hist: list[float] = []
        self._env = 0.0
        self._phase = 0.0
        self._t = 0.0
        self._sweep = 0.0
        self._lift = 0.0
        self._noise = random.Random(7)
        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # ── mode ──────────────────────────────────────────────
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        from voice import levels
        if mode in ("listen", "speak"):
            # fresh paper for each new voice
            self._hist = []
            self._env = 0.0
        if mode == "listen":
            levels.MIC.clear()
        if mode == "read":
            self._sweep = 0.0
        self._mode = mode
        if mode == "off":
            self._timer.stop()
        elif not self._timer.isActive():
            self._timer.start()
        self.update()

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setFixedHeight(26 if compact else 48)

    # ── the clock ─────────────────────────────────────────
    def _level(self) -> float:
        from voice import levels
        if self._mode == "listen":
            return levels.MIC.level()
        if self._mode == "speak":
            if levels.VOICE.live():
                return levels.VOICE.level()
            # A voice with no level feed (the system fallback voice): a calm,
            # speech-like cadence, so the trace still reads as "talking".
            t = self._t
            syll = 0.5 + 0.5 * math.sin(t * 9.0) * math.sin(t * 2.3 + 1.0)
            return 0.25 + 0.55 * max(0.0, syll)
        return 0.0

    def _tick(self) -> None:
        dt = self.FRAME_MS / 1000.0
        self._t += dt
        calm = style.reduced_motion()
        if self._mode in ("listen", "speak") and not calm:
            raw = self._level()
            # a room's hum shouldn't wiggle the pen; speech should fill it
            v = max(0.0, raw - 0.12) / 0.88
            v = min(1.0, v) ** 0.6
            k = 0.45 if v > self._env else 0.10           # quick attack, slow release
            self._env += (v - self._env) * k
            # a long, flowing stroke rather than a tight zigzag: a few swings
            # a second, quickening a little as the voice gets louder
            self._phase += 2 * math.pi * (3.0 + 1.8 * self._env) * dt
            tremor = 0.025 * math.sin(self._t * 4.1) + 0.01 * (self._noise.random() - 0.5)
            y = self._env * (0.88 * math.sin(self._phase)
                             + 0.12 * math.sin(self._phase * 2.1 + 1.3)) + tremor * (0.5 + self._env)
            self._hist.append(y)
            cap = int(self.width() / self.PX) + 8
            if len(self._hist) > cap:
                del self._hist[: len(self._hist) - cap]
            self._lift += (0.0 - self._lift) * 0.2
        elif self._mode == "read":
            self._sweep = (self._sweep + dt * 0.9) % 1.4
            self._lift += (1.0 - self._lift) * 0.15
        self.update()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self._mode != "off" and not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self._timer.stop()

    # ── painting ──────────────────────────────────────────
    def paintEvent(self, _e) -> None:
        if self._mode == "off":
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        nib_size = h * (0.62 if self._compact else 0.56)
        right = w - nib_size * 0.75            # room for the nib's body
        mid = h * (0.46 if self._compact else 0.42)
        amp = h * (0.30 if self._compact else 0.32)

        speak = self._mode == "speak"
        ink = QColor(style.accent()) if speak else QColor(style.INK_SOFT)
        wet = QColor(style.accent())
        base_w = 1.25 if self._compact else 1.7

        # the paper's rule: a faint baseline the pen returns to in silence
        rule = QColor(style.HAIRLINE)
        p.setPen(QPen(rule, 1.0))
        p.drawLine(QPointF(0, mid), QPointF(right, mid))

        hist = self._hist
        n = len(hist)
        pen = QPen()
        pen.setCapStyle(Qt.RoundCap)
        prev = None
        for k in range(n):
            # newest sample at the pen; older ones further left
            x = right - (n - 1 - k) * self.PX
            if x < -self.PX:
                continue
            y = mid - hist[k] * amp
            if prev is not None:
                px_, py_ = prev
                slope = abs(y - py_) / self.PX
                width = base_w * (0.55 + 0.6 * min(1.6, slope))
                col = QColor(ink)
                age = n - 1 - k
                if not speak and age < 24:
                    f = 1.0 - age / 24.0          # fresh ink, glossy, drying
                    col = QColor(int(ink.red() + (wet.red() - ink.red()) * f),
                                 int(ink.green() + (wet.green() - ink.green()) * f),
                                 int(ink.blue() + (wet.blue() - ink.blue()) * f))
                # the paper fades out toward the far edge
                col.setAlphaF(max(0.0, min(1.0, x / (w * 0.28))))
                if self._mode == "read":
                    # a light passing along what was said
                    sx = self._sweep / 1.2 * right
                    glow = max(0.0, 1.0 - abs(x - sx) / 36.0)
                    if glow > 0:
                        col = QColor(int(col.red() + (wet.red() - col.red()) * glow),
                                     int(col.green() + (wet.green() - col.green()) * glow),
                                     int(col.blue() + (wet.blue() - col.blue()) * glow),
                                     col.alpha())
                pen.setColor(col)
                pen.setWidthF(width)
                p.setPen(pen)
                p.drawLine(QPointF(px_, py_), QPointF(x, y))
            prev = (x, y)

        # the nib, at the pen point — lifted off the paper while reading back
        tip_y = mid - (hist[-1] * amp if hist else 0.0) - self._lift * h * 0.22
        acc = QColor(style.accent())
        _nib.paint(p, QPointF(right, tip_y), nib_size, acc, acc.darker(210))
