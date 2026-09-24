"""CORNER MIKE — the companion that stays when the workspace is away.

When FULL MIKE is minimised or closed, this small presence takes the corner:
the mark (alive with Mike's state), a slim line to keep talking, and — only
when there's something to say — what he's doing right now and what he said.
It never forces the whole application back over your work; it surfaces just
the relevant thing and recedes.

While Mike works, the corner says what he's doing in plain words, how long
it's been going, and offers Stop — the same trust the full window gives, in a
fraction of the space. A long answer is shown in part with a way to read the
rest in the full window, rather than clipped mid-line.

It implements the same contract the controller already speaks to a floating
companion (activate / dismiss / set_state / show_tool_status / append_response
/ finish / message_submitted / expand_requested / cancel_requested), so the
engine drives it with no new wiring.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mark import PresenceMark
from ui.workspace.icons import IconButton

#: How much of an answer the corner shows before offering the full window.
ANSWER_CHARS = 320

_STATE_TEXT = {
    "thinking": "Thinking…",
    "listening": "Listening…",
    "transcribing": "Transcribing…",
    "working": "Working…",
}
_BUSY = {"thinking", "working", "listening", "transcribing"}


class _CornerField(QLineEdit):
    def __init__(self, on_submit, parent=None) -> None:
        super().__init__(parent)
        self._on_submit = on_submit

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_submit()
            return
        super().keyPressEvent(e)


class CornerPresence(QWidget):

    message_submitted = Signal(str)
    expand_requested = Signal()
    cancel_requested = Signal()
    dismissed = Signal()

    WIDTH = 360
    MARGIN = 22
    SHADOW = 16

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._busy_since: float | None = None
        self._full_answer = ""
        self._build()
        self._clock = QTimer(self)
        self._clock.setInterval(500)
        self._clock.timeout.connect(self._tick)
        self.hide()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.SHADOW, self.SHADOW, self.SHADOW, self.SHADOW)
        outer.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("cornerCard")
        col = QVBoxLayout(self._card)
        col.setContentsMargins(14, 12, 10, 10)
        col.setSpacing(8)

        # ── what Mike is doing — only while he's doing something ──
        self._status_row = QWidget()
        srow = QHBoxLayout(self._status_row)
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(8)
        self._status = QLabel("")
        self._status.setFont(style.font(style.SMALL, QFont.Weight.Medium))
        self._status.setStyleSheet(f"color:{style.INK_SOFT};background:transparent;")
        srow.addWidget(self._status, 1)
        self._elapsed = QLabel("")
        self._elapsed.setFont(style.font(style.CAPTION))
        self._elapsed.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
        srow.addWidget(self._elapsed, 0, Qt.AlignVCenter)
        self._stop = IconButton("stop", "Stop Mike (Esc)", size=26, icon_size=16, variant="solid")
        self._stop.clicked.connect(self.cancel_requested.emit)
        srow.addWidget(self._stop, 0, Qt.AlignVCenter)
        self._status_row.hide()
        col.addWidget(self._status_row)

        # ── what Mike said ──
        self._answer = QLabel("")
        self._answer.setWordWrap(True)
        self._answer.setTextFormat(Qt.PlainText)
        self._answer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._answer.setFont(style.font(style.BODY))
        self._answer.setStyleSheet(f"color:{style.INK};background:transparent;")
        self._answer.hide()
        col.addWidget(self._answer)

        self._more = QLabel("")
        self._more.setFont(style.font(style.CAPTION, QFont.Weight.Medium))
        self._more.setCursor(Qt.PointingHandCursor)
        self._more.setStyleSheet(f"color:{style.accent()};background:transparent;")
        self._more.setText("Read the full answer in Mike →")
        self._more.mousePressEvent = lambda _e: self.expand_requested.emit()
        self._more.hide()
        col.addWidget(self._more)

        # ── the always-there row: mark, a line to talk, open, hide ──
        row = QHBoxLayout()
        row.setSpacing(8)
        self.mark = PresenceMark(24)
        row.addWidget(self.mark, 0, Qt.AlignVCenter)

        self._field = _CornerField(self._submit)
        self._field.setPlaceholderText("Ask Mike…")
        self._field.setFont(style.font(style.BODY))
        self._field.setFrame(False)
        self._field.setStyleSheet(
            f"QLineEdit{{background:transparent;border:none;color:{style.INK};"
            f"selection-background-color:{style.accent()};}}")
        row.addWidget(self._field, 1)

        self._expand = IconButton("expand", "Open Mike", size=28, icon_size=15)
        self._expand.clicked.connect(self.expand_requested.emit)
        row.addWidget(self._expand, 0, Qt.AlignVCenter)

        # A real way to send the corner away. Mike stays in the taskbar (the
        # window is minimised, not gone), so this dismisses the companion
        # without losing Mike — the taskbar or the hotkey brings him back.
        self._close = IconButton("close", "Hide the corner — Mike stays in the taskbar",
                                 size=28, icon_size=14)
        self._close.clicked.connect(self._dismiss_clicked)
        row.addWidget(self._close, 0, Qt.AlignVCenter)
        col.addLayout(row)

        outer.addWidget(self._card)

        self._card.setStyleSheet(
            f"QFrame#cornerCard{{background:{style.SURFACE};"
            f"border:1px solid {style.HAIRLINE};border-radius:16px;}}")

    # ── placement ─────────────────────────────────────────
    def _place(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self._card.adjustSize()
        height = self.sizeHint().height()
        w = self.WIDTH
        x = geo.right() - w - self.MARGIN + self.SHADOW
        y = geo.bottom() - height - self.MARGIN + self.SHADOW
        self.setGeometry(QRect(x, y, w, height))

    def _resize_to_content(self) -> None:
        QTimer.singleShot(0, self._place)

    # ── contract the controller drives ────────────────────
    def activate(self, start_listening: bool = False) -> None:
        self.clear_response()
        self._field.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self._field.setFocus()
        self._place()
        if start_listening:
            self.set_state("listening")

    def show_presence(self) -> None:
        """Come to the corner as a quiet companion (no focus stealing)."""
        self.clear_response()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._place()

    def dismiss(self) -> None:
        self.hide()
        self.clear_response()
        self.mark.set_state("idle")

    def set_state(self, state: str, status: str = "") -> None:
        self.mark.set_state("listening" if state == "transcribing" else state)
        text = status or _STATE_TEXT.get(state, "")
        if text:
            self._show_status(text, busy=state in _BUSY)
        elif state == "speaking":
            self._hide_status()

    def show_tool_status(self, text: str) -> None:
        self.mark.set_state("working")
        self._show_status(text, busy=True)

    def show_tool_done(self, text: str, success: bool = True) -> None:
        pass

    def set_response(self, text: str) -> None:
        self._full_answer = text
        self._hide_status()
        self._render_answer()

    def append_response(self, token: str) -> None:
        if self._status_row.isVisible():
            # the answer arriving is the end of "working on it"
            self._hide_status()
        self._full_answer += token
        self._render_answer()

    def clear_response(self) -> None:
        self._full_answer = ""
        self._answer.setText("")
        self._answer.hide()
        self._more.hide()
        self._hide_status()
        self._resize_to_content()

    def finish(self) -> None:
        self.mark.set_state("idle")
        self._hide_status()

    # ── internals ─────────────────────────────────────────
    def _render_answer(self) -> None:
        text = self._full_answer.strip()
        if not text:
            self._answer.hide()
            self._more.hide()
            return
        long = len(text) > ANSWER_CHARS
        if long:
            cut = text[:ANSWER_CHARS].rsplit(" ", 1)[0].rstrip(",.;: ")
            text = cut + "…"
        self._answer.setText(text)
        self._answer.show()
        self._more.setVisible(long)
        self._resize_to_content()

    def _show_status(self, text: str, busy: bool) -> None:
        self._status.setText(" ".join(text.split())[:70])
        self._stop.setVisible(busy and not text.startswith("Listening"))
        if busy and self._busy_since is None:
            self._busy_since = time.monotonic()
        if not busy:
            self._busy_since = None
        self._tick()
        if busy:
            self._clock.start()
        self._status_row.show()
        self._resize_to_content()

    def _hide_status(self) -> None:
        self._busy_since = None
        self._clock.stop()
        self._elapsed.setText("")
        if self._status_row.isVisible():
            self._status_row.hide()
            self._resize_to_content()

    def _tick(self) -> None:
        if self._busy_since is None:
            self._elapsed.setText("")
            return
        secs = int(time.monotonic() - self._busy_since)
        self._elapsed.setText(f"{secs}s" if secs >= 2 else "")

    def _dismiss_clicked(self) -> None:
        self.dismiss()
        self.dismissed.emit()

    def _submit(self) -> None:
        text = self._field.text().strip()
        if text:
            self._field.clear()
            self.message_submitted.emit(text)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.cancel_requested.emit()
            self.dismiss()
            return
        super().keyPressEvent(event)

    # ── the floating material: a soft shadowed card ───────
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        m = self.SHADOW
        radius = 16.0
        bx, by = m, m
        bw, bh = self.width() - 2 * m, self.height() - 2 * m
        for i in range(m, 0, -2):
            a = int(3 + 34 * (1 - i / m) ** 2.2)
            sh = QPainterPath()
            sh.addRoundedRect(bx - i, by - i + 4, bw + 2 * i, bh + 2 * i,
                              radius + i, radius + i)
            p.fillPath(sh, QColor(0, 0, 0, a))
