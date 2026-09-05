"""The aura — edge-lighting for as long as Mike is actually with you.

⌘⇧Space, the edge strip clicked, or the wake word. A soft amber glow along
the screen's own edges rises the moment Mike is summoned, settles into a
quiet ambient presence for as long as the invocation line is open or a task
is running, and only fades once the exchange is genuinely finished — a
response has landed, or it's dismissed. Not a 600ms flash: a state, driven
by the same lifecycle calls (`activate` / `finish` / `dismiss`) the rest of
the invocation line already goes through. Click-through, no window chrome,
same amber as the dial everywhere else so it reads as Mike.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from ui.home import motion
from ui.instrument import tokens

_FPS = 60
_RISE = 0.16       # 0 -> peak, the "I heard you" beat
_SETTLE = 0.35     # peak -> ambient, easing down to something sustainable
_FADE_OUT = 0.42   # ambient -> 0, on release()
_DEPTH = 140
_PEAK_ALPHA = 0.34
_AMBIENT_ALPHA = 0.24

_PHASE_IDLE = "idle"
_PHASE_RISE = "rise"
_PHASE_SETTLE = "settle"
_PHASE_HELD = "held"
_PHASE_LEAVE = "leave"


class Aura(QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._phase = _PHASE_IDLE
        self._t0 = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(1000 // _FPS)
        self._timer.timeout.connect(self._tick)

    def pulse(self) -> None:
        """Mike has been summoned. Idempotent — re-summoning while already
        lit (e.g. the wake word firing while the line is still open) just
        keeps the current glow rather than restarting the rise."""

        if self._phase in (_PHASE_RISE, _PHASE_SETTLE, _PHASE_HELD):
            return

        if motion.reduced_motion():
            self._phase = _PHASE_HELD
            self._show_static()
            return

        screen = QApplication.primaryScreen()
        if screen is None:
            return
        self.setGeometry(screen.geometry())
        self._phase = _PHASE_RISE
        self._t0 = time.monotonic()
        self.show()
        self.raise_()
        self._timer.start()
        self.update()

    def release(self) -> None:
        """The exchange is genuinely done — a response landed, or it was
        dismissed. Fades the ambient glow out; harmless if already off."""

        if self._phase == _PHASE_IDLE:
            return
        if motion.reduced_motion():
            self._phase = _PHASE_IDLE
            self.hide()
            return
        self._phase = _PHASE_LEAVE
        self._t0 = time.monotonic()
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def _show_static(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        self.setGeometry(screen.geometry())
        self.show()
        self.raise_()
        self.update()

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._t0

        if self._phase == _PHASE_RISE and elapsed >= _RISE:
            self._phase = _PHASE_SETTLE
            self._t0 = time.monotonic()
            elapsed = 0.0

        if self._phase == _PHASE_SETTLE and elapsed >= _SETTLE:
            self._phase = _PHASE_HELD
            # Ambient level is static — stop repainting every frame while
            # nothing is changing. release() restarts the timer for the
            # fade-out.
            self._timer.stop()
            self.update()
            return

        if self._phase == _PHASE_LEAVE and elapsed >= _FADE_OUT:
            self._phase = _PHASE_IDLE
            self._timer.stop()
            self.hide()
            return

        self.update()

    def _alpha(self) -> float:
        elapsed = time.monotonic() - self._t0

        if self._phase == _PHASE_RISE:
            return _PEAK_ALPHA * min(1.0, elapsed / _RISE)
        if self._phase == _PHASE_SETTLE:
            t = min(1.0, elapsed / _SETTLE)
            return _PEAK_ALPHA + (_AMBIENT_ALPHA - _PEAK_ALPHA) * t
        if self._phase == _PHASE_HELD:
            return _AMBIENT_ALPHA
        if self._phase == _PHASE_LEAVE:
            t = min(1.0, elapsed / _FADE_OUT)
            return _AMBIENT_ALPHA * (1.0 - t)
        return 0.0

    def paintEvent(self, event) -> None:
        if self._phase == _PHASE_IDLE:
            return
        alpha = self._alpha()
        if alpha <= 0.002:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        hi = QColor(tokens.AMBER)
        hi.setAlphaF(alpha)
        lo = QColor(tokens.AMBER)
        lo.setAlphaF(0.0)

        top = QLinearGradient(0, 0, 0, _DEPTH)
        top.setColorAt(0, hi); top.setColorAt(1, lo)
        painter.fillRect(QRectF(0, 0, w, _DEPTH), top)

        bottom = QLinearGradient(0, h, 0, h - _DEPTH)
        bottom.setColorAt(0, hi); bottom.setColorAt(1, lo)
        painter.fillRect(QRectF(0, h - _DEPTH, w, _DEPTH), bottom)

        left = QLinearGradient(0, 0, _DEPTH, 0)
        left.setColorAt(0, hi); left.setColorAt(1, lo)
        painter.fillRect(QRectF(0, 0, _DEPTH, h), left)

        right = QLinearGradient(w, 0, w - _DEPTH, 0)
        right.setColorAt(0, hi); right.setColorAt(1, lo)
        painter.fillRect(QRectF(w - _DEPTH, 0, _DEPTH, h), right)
