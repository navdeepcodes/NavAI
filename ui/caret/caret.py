"""The caret — Mike's identity at every depth.

One rectangle. Its colour says what kind of state Mike is in; its motion says
which one. Every behaviour here is driven by a signal the runtime already
emits, so the caret can never animate about work that isn't happening.

Sizes: 3x15 in the edge and composers, 6x32 at the head of the Home column.
Same object throughout — that is the point of the direction.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from ui.caret import tokens
from ui.home import motion

# Only these states move. Anything else is painted once and left alone —
# a still caret is a real state, not a missing animation.
_ANIMATED = {"idle", "listening", "thinking", "working", "responding"}

_FPS = 30


class Caret(QWidget):
    """A caret that reflects one runtime state."""

    clicked = Signal()

    def __init__(
        self,
        width: int = tokens.CARET_W,
        height: int = tokens.CARET_H,
        parent=None,
        clickable: bool = False,
    ) -> None:
        super().__init__(parent)

        self._w = width
        self._h = height
        self._state = "idle"
        self._clickable = clickable
        self._t0 = time.monotonic()

        # Travel and stretch need room to move without clipping.
        self.setFixedSize(width + 2, int(height * 1.5) + 6)
        self.setAttribute(Qt.WA_TranslucentBackground)

        if clickable:
            self.setCursor(Qt.PointingHandCursor)

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
        """Runs only while a moving state is actually on screen."""
        should_run = (
            self._state in _ANIMATED
            and self.isVisible()
            and not motion.reduced_motion()
        )
        if should_run and not self._timer.isActive():
            self._timer.start()
        elif not should_run and self._timer.isActive():
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
        painter.setRenderHint(QPainter.Antialiasing, False)

        elapsed = time.monotonic() - self._t0
        colour = QColor(tokens.CARET_TONE.get(self._state, tokens.INDIGO))

        height = float(self._h)
        offset = 0.0
        alpha = 1.0

        if motion.reduced_motion():
            pass

        elif self._state == "idle":
            # Slow breath. The resting state of a machine that is on.
            alpha = 0.5 + 0.5 * (0.5 + 0.5 * math.sin(elapsed * 2 * math.pi / 3.6))

        elif self._state == "listening":
            # Stretches to show the mic is open. The voice engine exposes no
            # amplitude, so this is a steady rhythm, not a level meter —
            # it claims "open", never "this loud".
            height = self._h * (0.62 + 0.68 * (0.5 + 0.5 * math.sin(elapsed * 2 * math.pi / 0.9)))

        elif self._state == "thinking":
            # Compressed and jittering inward: activity without progress,
            # because there is no progress to report.
            step = int(elapsed / 0.28) % 2
            height = self._h * (0.66 if step else 0.9)
            alpha = 0.62 if step else 1.0

        elif self._state == "working":
            # Travels down the baseline. Directional, because a tool call is
            # a step forward — but it never implies how many are left.
            phase = (elapsed % 1.4) / 1.4
            offset = 5.0 * (0.5 - 0.5 * math.cos(phase * 2 * math.pi))
            alpha = 1.0 - 0.42 * (0.5 - 0.5 * math.cos(phase * 2 * math.pi))

        elif self._state == "responding":
            alpha = 1.0 if (elapsed % 1.0) < 0.55 else 0.18

        elif self._state == "error":
            # One hard displacement, then still.
            offset = 3.0 if elapsed < 0.12 else 0.0

        colour.setAlphaF(max(0.0, min(1.0, alpha)))

        x = (self.width() - self._w) / 2.0
        y = (self.height() - height) / 2.0 + offset

        painter.fillRect(
            int(round(x)),
            int(round(y)),
            self._w,
            int(round(height)),
            colour,
        )

    # ── Interaction ──────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if self._clickable and event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)
