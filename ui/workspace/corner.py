"""CORNER MIKE — the companion that stays when the workspace is away.

When FULL MIKE is minimised or closed, this small presence takes the corner:
the mark (alive with Mike's state), a slim line to keep talking, and — only
when there's something to say — a patch of text that emerges for a status or a
reply. It never forces the whole application back over your work; it surfaces
just the relevant thing and recedes.

It implements the same contract the controller already speaks to a floating
companion (activate / dismiss / set_state / show_tool_status / append_response
/ finish / message_submitted / expand_requested), so the engine drives it with
no new wiring — the old brass InvokeLine is simply replaced by a presence that
belongs to the same product as the workspace.
"""
from __future__ import annotations

from PySide6.QtCore import (
    Qt, QEasingCurve, QPropertyAnimation, QRect, QTimer, Signal,
)
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mark import PresenceMark


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

    WIDTH = 340
    MARGIN = 22
    SHADOW = 16

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._build()
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.hide()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.SHADOW, self.SHADOW, self.SHADOW, self.SHADOW)
        outer.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("cornerCard")
        col = QVBoxLayout(self._card)
        col.setContentsMargins(14, 12, 12, 12)
        col.setSpacing(8)

        # ── what Mike is doing / saying — only when there's something ──
        self._status = QLabel("")
        self._status.setFont(style.label(10))
        self._status.setStyleSheet(
            f"color:{style.INK_MUTE};background:transparent;letter-spacing:0.5px;")
        self._status.hide()
        col.addWidget(self._status)

        self._answer = QLabel("")
        self._answer.setWordWrap(True)
        self._answer.setFont(style.voice(13))
        self._answer.setStyleSheet(
            f"color:{style.INK};background:transparent;line-height:148%;")
        self._answer.setMaximumHeight(180)
        self._answer.hide()
        col.addWidget(self._answer)

        # ── the always-there row: mark, a line to talk, expand ──
        row = QHBoxLayout()
        row.setSpacing(10)
        self.mark = PresenceMark(24)
        row.addWidget(self.mark, 0, Qt.AlignVCenter)

        self._field = _CornerField(self._submit)
        self._field.setPlaceholderText("Ask Mike…")
        self._field.setFont(style.voice(13))
        self._field.setFrame(False)
        self._field.setStyleSheet(
            f"QLineEdit{{background:transparent;border:none;color:{style.INK};"
            f"selection-background-color:{style.accent()};}}"
            f"QLineEdit::placeholder{{color:{style.INK_MUTE};}}")
        row.addWidget(self._field, 1)

        self._expand = QLabel("⤢")
        self._expand.setObjectName("cornerExpand")
        self._expand.setCursor(Qt.PointingHandCursor)
        self._expand.setToolTip("Open full Mike")
        self._expand.setStyleSheet(
            f"color:{style.INK_MUTE};background:transparent;font-size:15px;")
        self._expand.mousePressEvent = lambda _e: self.expand_requested.emit()
        row.addWidget(self._expand, 0, Qt.AlignVCenter)

        # A real way to send the corner away. Mike stays in the taskbar (the
        # window is minimised, not gone), so this dismisses the companion
        # without losing Mike — the taskbar or the hotkey brings him back.
        self._close = QLabel("✕")
        self._close.setObjectName("cornerClose")
        self._close.setCursor(Qt.PointingHandCursor)
        self._close.setToolTip("Hide the corner (Mike stays in the taskbar)")
        self._close.setStyleSheet(
            f"color:{style.INK_MUTE};background:transparent;font-size:14px;")
        self._close.mousePressEvent = lambda _e: self._dismiss_clicked()
        row.addWidget(self._close, 0, Qt.AlignVCenter)
        col.addLayout(row)

        outer.addWidget(self._card)

        self._card.setStyleSheet(
            f"QFrame#cornerCard{{background:{style.GROUND};"
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
            self.mark.set_state("listening")

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
        self.mark.set_state(state)
        if status:
            self._show_status(status)

    def show_tool_status(self, text: str) -> None:
        self.mark.set_state("working")
        self._show_status(text)

    def show_tool_done(self, text: str, success: bool = True) -> None:
        pass

    def set_response(self, text: str) -> None:
        self._answer.setText(text)
        self._answer.show()
        self._resize_to_content()

    def append_response(self, token: str) -> None:
        if not self._answer.isVisible():
            self._answer.show()
        self._answer.setText(self._answer.text() + token)
        self._resize_to_content()

    def clear_response(self) -> None:
        self._answer.setText("")
        self._answer.hide()
        self._status.setText("")
        self._status.hide()
        self._resize_to_content()

    def finish(self) -> None:
        self.mark.set_state("idle")

    def _show_status(self, text: str) -> None:
        self._status.setText(" ".join(text.split())[:60].upper())
        self._status.show()
        self._resize_to_content()

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
