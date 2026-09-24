"""The pen that writes Mike's answers.

While a reply streams in, the nib sits at the end of the text as if it were
writing it: it glides to each new word, makes the small quick movements of a
hand forming letters while words are arriving, rests when they pause, and
lifts away and fades when the answer is complete.

It lives on the conversation column rather than inside the reply, so the nib
(which hangs below and to the right of its tip) is never clipped by the
reply's own tight bounds.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QPointF, QTimer
from PySide6.QtGui import QColor, QPainter, QTextCursor
from PySide6.QtWidgets import QWidget

from ui.panel import style
from ui.workspace import nib as _nib


class StreamingPen(QWidget):
    """A nib that follows the end of a streaming reply."""

    SIZE = 26          # the nib's height, px
    BOX = 44           # the widget's square; the tip sits near its top-left

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setFixedSize(self.BOX, self.BOX)
        self.setAttribute(__import__("PySide6").QtCore.Qt.WA_TransparentForMouseEvents, True)
        self._turn = None
        self._pos = QPointF(0, 0)          # current tip, host coords
        self._target = QPointF(0, 0)
        self._opacity = 0.0
        self._fade_to = 0.0
        self._last_growth = 0.0
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.hide()

    # ── following a reply ─────────────────────────────────
    def follow(self, turn) -> None:
        if self._turn is not None:
            try:
                self._turn.textChanged.disconnect(self._on_text)
            except (TypeError, RuntimeError):
                pass
        self._turn = turn
        turn.textChanged.connect(self._on_text)
        self._fade_to = 0.0
        self._opacity = 0.0
        self._place(snap=True)

    def lift(self) -> None:
        """The answer is done: raise the pen off the page and let it go."""
        self._fade_to = 0.0
        if self.isVisible() and not self._timer.isActive():
            self._timer.start()

    def _on_text(self) -> None:
        turn = self._turn
        if turn is None:
            return
        if not getattr(turn, "_streaming", False):
            self.lift()
            return
        self._last_growth = time.monotonic()
        self._fade_to = 1.0
        self._place()

    def _end_point(self) -> QPointF | None:
        turn = self._turn
        try:
            if turn is None or not turn.isVisible():
                return None
        except RuntimeError:          # the reply was deleted (a new chat)
            self._turn = None
            return None
        cur = QTextCursor(turn.document())
        cur.movePosition(QTextCursor.End)
        rect = turn.cursorRect(cur)
        local = QPoint(rect.right() + 3, rect.bottom() - max(3, rect.height() // 4))
        return QPointF(turn.viewport().mapTo(self.parentWidget(), local))

    def _place(self, snap: bool = False) -> None:
        end = self._end_point()
        if end is None:
            return
        self._target = end
        if snap or self._opacity <= 0.01:
            self._pos = QPointF(end)
        if style.reduced_motion():
            # Calm mode: no pen gliding across the page.
            self._fade_to = 0.0
        self.show()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start()
        self._sync_geometry()

    # ── motion ────────────────────────────────────────────
    def _tick(self) -> None:
        self._t += 0.016
        # glide toward the newest word, quickly but not instantly
        self._pos += (self._target - self._pos) * 0.28
        self._opacity += (self._fade_to - self._opacity) * 0.18
        if self._fade_to == 0.0 and self._opacity < 0.02:
            self._opacity = 0.0
            self._timer.stop()
            self.hide()
            return
        self._sync_geometry()
        self.update()

    def _writing(self) -> bool:
        return time.monotonic() - self._last_growth < 0.35

    def _sync_geometry(self) -> None:
        self.move(int(self._pos.x()) - 4, int(self._pos.y()) - 4)

    def paintEvent(self, _e) -> None:
        if self._opacity <= 0.0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setOpacity(self._opacity)
        # tip at (4, 4) in widget space, plus the small movements of a hand
        # forming letters while words are arriving; still when they pause
        jx = jy = 0.0
        tilt = 0.0
        if self._writing():
            jx = 1.6 * math.sin(self._t * 23.0) + 0.8 * math.sin(self._t * 37.0)
            jy = 1.3 * math.sin(self._t * 29.0 + 1.1)
            tilt = 3.0 * math.sin(self._t * 11.0)
        lift = (1.0 - self._opacity) * 10.0          # rises as it fades out
        tip = QPointF(4 + jx + lift * 0.4, 4 + jy - lift)
        acc = QColor(style.accent())
        _nib.paint(p, tip, self.SIZE, acc, acc.darker(210), _nib.ANGLE + tilt)
