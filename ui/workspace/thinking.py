"""The wait, made to feel like a mind at work.

Not a spinner and not a static dot. A short thought writes itself out a
character at a time, holds for a breath, then fades away, and the next one
writes in — continuously, so a long wait reads as Mike actively turning
something over rather than a process that has hung.

Three things carry it, all derived from one continuous clock so nothing
steps or stutters:

  - the reveal: characters appear left to right, like typing;
  - the caret: a thin accent bar that blinks while the thought rests;
  - the fade: the finished thought dissolves, and a new one begins.

Deliberately quiet — INK_SOFT text, a hair of accent on the caret, the UI
font at reading size. The restraint is the point: it should feel premium and
alive, never like a toy loader.
"""
from __future__ import annotations

import random

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from ui.panel import style


# Short thoughts in Mike's register — a smart person half-answering you from
# the next room, not a status bar. No jokes (they wear out on the fourth read),
# nothing cutesy. The last two are held back for waits long enough to want
# reassurance rather than novelty.
THOUGHTS = (
    "Thinking it through",
    "Working it out",
    "Looking at this",
    "Piecing it together",
    "Following the thread",
    "Checking the details",
    "Turning it over",
    "Lining things up",
    "Reading it carefully",
    "Making sense of it",
    "Getting the shape of it",
    # reassurance tail
    "Almost there",
    "Nearly done",
)
_REASSURING_TAIL = 2


class ThinkingLine(QWidget):
    """A single line that writes a thought, holds it, fades it, and repeats."""

    # phase durations, seconds
    _CHAR_S = 0.032        # per character while writing
    _HOLD_S = 0.85         # full thought held before it fades
    _FADE_S = 0.34         # dissolve
    _GAP_S = 0.14          # blank beat before the next one
    _FRAME_MS = 16         # ~60fps; motion never reads as stepping
    _LONG_WAIT_S = 11.0    # past here, stay on the reassuring tail

    def __init__(self, size: int = 15, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedHeight(int(size * 1.9))
        self._t = 0.0                 # continuous clock, seconds
        self._elapsed = 0.0           # total time thinking, for the long-wait bias
        self._phase = "write"         # write | hold | fade | gap
        self._phase_start = 0.0
        self._index = random.randrange(len(THOUGHTS) - _REASSURING_TAIL)
        self._frame = QTimer(self)
        self._frame.timeout.connect(self._on_frame)

    # ── lifecycle ─────────────────────────────────────────
    def start(self) -> None:
        self._t = 0.0
        self._elapsed = 0.0
        self._phase = "write"
        self._phase_start = 0.0
        self._pick_first()
        if not self._frame.isActive():
            self._frame.start(self._FRAME_MS)

    def stop(self) -> None:
        # Timers hold a reference to a widget the page is about to delete;
        # stopping explicitly keeps a tick from firing into a torn-down widget.
        self._frame.stop()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if not self._frame.isActive():
            self.start()

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self._frame.stop()

    # ── the clock ─────────────────────────────────────────
    def _pick_first(self) -> None:
        body = len(THOUGHTS) - _REASSURING_TAIL
        self._index = random.randrange(body)

    def _next_thought(self) -> None:
        body = len(THOUGHTS) - _REASSURING_TAIL
        if self._elapsed >= self._LONG_WAIT_S:
            # Long wait: settle onto the reassuring tail instead of implying
            # fresh activity that isn't happening.
            self._index = body + ((self._index + 1) % _REASSURING_TAIL)
            return
        choice = self._index
        while choice == self._index and body > 1:
            choice = random.randrange(body)
        self._index = choice

    def _on_frame(self) -> None:
        self._t += self._FRAME_MS / 1000.0
        self._elapsed += self._FRAME_MS / 1000.0

        text = THOUGHTS[self._index]
        since = self._t - self._phase_start
        if self._phase == "write":
            if since >= len(text) * self._CHAR_S:
                self._phase, self._phase_start = "hold", self._t
        elif self._phase == "hold":
            if since >= self._HOLD_S:
                self._phase, self._phase_start = "fade", self._t
        elif self._phase == "fade":
            if since >= self._FADE_S:
                self._phase, self._phase_start = "gap", self._t
        elif self._phase == "gap":
            if since >= self._GAP_S:
                self._next_thought()
                self._phase, self._phase_start = "write", self._t
        self.update()

    # ── painting ──────────────────────────────────────────
    def paintEvent(self, _e) -> None:
        text = THOUGHTS[self._index]
        since = self._t - self._phase_start

        # how much of the thought is written, and how visible the whole line is
        if self._phase == "write":
            shown = min(len(text), int(since / self._CHAR_S) + 1)
            opacity = 1.0
        elif self._phase == "hold":
            shown, opacity = len(text), 1.0
        elif self._phase == "fade":
            shown = len(text)
            opacity = max(0.0, 1.0 - since / self._FADE_S)
        else:  # gap
            shown, opacity = 0, 0.0
        if opacity <= 0.001:
            return

        visible = text[:shown]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        font = style.voice(self._size)
        p.setFont(font)
        fm = p.fontMetrics()
        baseline = self.height() / 2.0 + (fm.ascent() - fm.descent()) / 2.0

        ink = QColor(style.INK_SOFT)
        ink.setAlphaF(opacity)
        path = QPainterPath()
        path.addText(QPointF(1.0, baseline), font, visible)
        p.fillPath(path, QBrush(ink))

        # the caret: solid while writing, a slow blink while the thought rests,
        # riding just after the last written glyph.
        if self._phase in ("write", "hold"):
            blink = 1.0
            if self._phase == "hold":
                # ~1.1s blink cycle
                import math
                blink = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(since * 5.6))
            caret = QColor(style.accent())
            caret.setAlphaF(opacity * blink)
            x = 1.0 + fm.horizontalAdvance(visible) + 2.0
            top = baseline - fm.ascent() + 2.0
            bottom = baseline + 2.0
            p.fillRect(int(x), int(top), 2, int(bottom - top), caret)
