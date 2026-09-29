"""The voice meter -- live level bars for your voice and Mike's.

A row of rounded bars, mirrored about a centre line, scrolling right to left:
each new bar is the real loudness of the moment (voice.levels), so you can
see yourself being heard, and see when you've stopped. Quiet is a row of
small dots; speech lifts them.

    listen   your microphone, in the ink colour
    read     the bars hold still while what you said is transcribed, and a
             soft light passes along them
    speak    Mike's own voice as it actually plays, in a softer tone

With Reduce motion on, the bars rest as a still row.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from ui.panel import style


class VoiceTrace(QWidget):

    FRAME_MS = 16
    #: A new bar this often: fast enough to follow syllables, slow enough to read.
    SAMPLE_S = 0.055

    def __init__(self, compact: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._compact = compact
        self.setFixedHeight(26 if compact else 44)
        self.setMinimumWidth(120)
        self._mode = "off"
        self._hist: list[float] = []      # one level (0..1) per bar, newest last
        self._env = 0.0
        self._t = 0.0
        self._since_sample = 0.0
        self._sweep = 0.0
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
            self._hist = []               # a fresh row for each new voice
            self._env = 0.0
            self._since_sample = 0.0
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
        self.setFixedHeight(26 if compact else 44)

    # ── geometry ──────────────────────────────────────────
    def _bar(self) -> tuple[float, float]:
        """(bar width, gap) in px."""
        return (2.5, 2.5) if self._compact else (3.0, 3.0)

    def _capacity(self) -> int:
        bar, gap = self._bar()
        return max(8, int(self.width() / (bar + gap)) + 2)

    # ── the clock ─────────────────────────────────────────
    def _level(self) -> float:
        from voice import levels
        if self._mode == "listen":
            return levels.MIC.level()
        if self._mode == "speak":
            if levels.VOICE.live():
                return levels.VOICE.level()
            # A voice with no level feed (the system fallback voice): a calm,
            # speech-like cadence, so the bars still read as "talking".
            t = self._t
            syll = 0.5 + 0.5 * math.sin(t * 9.0) * math.sin(t * 2.3 + 1.0)
            return 0.25 + 0.55 * max(0.0, syll)
        return 0.0

    def _tick(self) -> None:
        dt = self.FRAME_MS / 1000.0
        self._t += dt
        if self._mode in ("listen", "speak") and not style.reduced_motion():
            raw = self._level()
            # a room's hum shouldn't lift the bars; speech should fill them
            v = min(1.0, max(0.0, raw - 0.12) / 0.88) ** 0.6
            k = 0.55 if v > self._env else 0.18           # quick attack, gentle release
            self._env += (v - self._env) * k
            self._since_sample += dt
            while self._since_sample >= self.SAMPLE_S:
                self._since_sample -= self.SAMPLE_S
                self._hist.append(self._env)
            cap = self._capacity()
            if len(self._hist) > cap:
                del self._hist[: len(self._hist) - cap]
        elif self._mode == "read":
            self._sweep = (self._sweep + dt * 0.8) % 1.3
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
        p.setPen(Qt.NoPen)
        w, h = float(self.width()), float(self.height())
        bar, gap = self._bar()
        step = bar + gap
        mid = h / 2.0
        tallest = h * 0.86
        colour = QColor(style.INK if self._mode != "speak" else style.INK_SOFT)

        hist = self._hist
        n = self._capacity()
        # Scroll smoothly between samples: the row slides left by the part of
        # a step that has passed since the newest bar arrived.
        slide = 0.0
        if self._mode in ("listen", "speak") and not style.reduced_motion():
            slide = (self._since_sample / self.SAMPLE_S) * step
        right = w - bar - 2.0
        for i in range(n):
            k = len(hist) - 1 - i                 # i = 0 is the newest bar, at the right
            level = hist[k] if k >= 0 else 0.0
            x = right - i * step - slide
            if x < -bar:
                break
            height = max(bar, bar + (tallest - bar) * level)
            col = QColor(colour)
            # the row fades in from the far edge
            alpha = max(0.0, min(1.0, x / (w * 0.22)))
            if self._mode == "read":
                # held still, a soft light passing along what was said
                sx = (self._sweep / 1.1) * w
                glow = max(0.0, 1.0 - abs(x - sx) / 60.0)
                alpha *= 0.45 + 0.55 * glow
            col.setAlphaF(alpha * (0.55 + 0.45 * min(1.0, level * 1.6 + 0.2)))
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x, mid - height / 2.0, bar, height), bar / 2.0, bar / 2.0)
