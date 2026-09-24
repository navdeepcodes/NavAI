"""The wait, written by hand.

While Mike thinks, the nib writes what he's doing — "Thinking it through",
"Piecing it together" — in real handwriting, stroke by stroke, the ink landing
glossy and drying as it goes. The thought holds for a breath, fades from the
page, and the next one is written. A long wait settles onto reassurance
("Almost there") and shows how long it's been, because a clock that keeps
moving is the honest difference between slow and stuck.

Built on ui.workspace.handwriting (Hershey pen strokes, broad-nib ink) and the
same nib drawing as the app's mark, so the pen you see thinking is the logo.
With Reduce motion on, the thought is simply shown, written, with the pen at
rest.
"""
from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from ui.panel import style
from ui.workspace import handwriting as hw


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
    """A thought, handwritten by the nib, held, faded, and replaced."""

    _HOLD_S = 1.1          # the finished thought rests before it fades
    _FADE_S = 0.45
    _GAP_S = 0.25
    _FRAME_MS = 16
    _LONG_WAIT_S = 11.0    # past here, stay on the reassuring tail
    _SHOW_ELAPSED_S = 8.0  # past here, also show how long it's been
    _PACE = 1.35           # a little quicker than a careful hand

    def __init__(self, size: int = 16, parent=None) -> None:
        super().__init__(parent)
        self._size = size                       # the text's reading size, px
        # handwriting sits a little larger than type, like a note in the margin
        self._scale = size * 1.55 / 21.0        # px per Hershey unit
        self.setFixedHeight(int(size * 3.4))
        self._t = 0.0
        self._elapsed = 0.0
        self._phase = "write"
        self._phase_start = 0.0
        self._index = 0
        self._script: hw.Script | None = None
        self._frame = QTimer(self)
        self._frame.timeout.connect(self._on_frame)
        self._pick_first()

    # ── lifecycle ─────────────────────────────────────────
    def start(self) -> None:
        self._t = 0.0
        self._elapsed = 0.0
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
            self._frame.start(self._FRAME_MS)

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self._frame.stop()

    # ── the clock ─────────────────────────────────────────
    def _set(self, index: int) -> None:
        self._index = index
        self._script = hw.Script(THOUGHTS[index]) if hw.available() else None
        self._phase, self._phase_start = "write", self._t

    def _pick_first(self) -> None:
        self._set(random.randrange(len(THOUGHTS) - _REASSURING_TAIL))

    def _next_thought(self) -> None:
        body = len(THOUGHTS) - _REASSURING_TAIL
        if self._elapsed >= self._LONG_WAIT_S:
            # Long wait: settle onto the reassuring tail instead of implying
            # fresh activity that isn't happening.
            self._set(body + ((self._index + 1) % _REASSURING_TAIL)
                      if self._index >= body else body)
            return
        choice = self._index
        while choice == self._index and body > 1:
            choice = random.randrange(body)
        self._set(choice)

    def _write_time(self) -> float:
        return (self._script.duration / self._PACE) if self._script else 1.2

    def _on_frame(self) -> None:
        dt = self._FRAME_MS / 1000.0
        self._t += dt
        self._elapsed += dt
        if style.reduced_motion():
            self._phase, self._phase_start = "hold", self._t
            self.update()
            return
        since = self._t - self._phase_start
        if self._phase == "write" and since >= self._write_time():
            self._phase, self._phase_start = "hold", self._t
        elif self._phase == "hold" and since >= self._HOLD_S:
            self._phase, self._phase_start = "fade", self._t
        elif self._phase == "fade" and since >= self._FADE_S:
            self._phase, self._phase_start = "gap", self._t
        elif self._phase == "gap" and since >= self._GAP_S:
            self._next_thought()
        self.update()

    # ── painting ──────────────────────────────────────────
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        sc = self._scale
        baseline = QPointF(4.0, self.height() * 0.62)
        ink = QColor(style.INK_SOFT)
        wet = QColor(style.accent())
        since = self._t - self._phase_start

        # how long it's been, at a fixed place so the number stays readable
        if self._elapsed >= self._SHOW_ELAPSED_S:
            secs = int(self._elapsed)
            label = f"{secs}s" if secs < 60 else f"{secs // 60}m {secs % 60:02d}s"
            p.setFont(style.font(style.CAPTION))
            p.setPen(QColor(style.INK_MUTE))
            widest = 330.0 * sc
            p.drawText(int(baseline.x() + widest + 26), int(baseline.y()), label)

        if self._script is None:
            # no stroke data: a plain, honest line rather than nothing
            p.setFont(style.font(self._size))
            p.setPen(ink)
            p.drawText(int(baseline.x()), int(baseline.y()), THOUGHTS[self._index])
            return

        script = self._script
        if self._phase == "write":
            t, opacity, pen = since * self._PACE, 1.0, True
        elif self._phase == "hold":
            t, opacity, pen = script.duration + 1.0, 1.0, True
        elif self._phase == "fade":
            t, opacity, pen = script.duration + 1.0, max(0.0, 1.0 - since / self._FADE_S), False
        else:
            return

        tip = script.paint(p, baseline, sc, t, ink, wet, opacity)
        if pen:
            _x, _y, down = script.pen_at(t)
            resting = self._phase == "hold"
            if resting:
                # pen lifted off the page at the end of the thought, poised
                down = False
            hw.paint_pen(p, tip, self._size * 2.3, QColor(style.accent()),
                         QColor(style.accent()).darker(210), down)
