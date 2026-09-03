"""D2 — invocation. Deliberate, and therefore allowed to take focus.

⌘⇧Space or the wake word from anywhere. One line, no title bar, no send
button, no mic icon: Return submits, Escape dismisses. Mike arrives as a
caret and the line unrolls from it, so the presence precedes the interface.

If an answer is short it renders here. If it isn't, the edge carries it and
this closes — Mike hands the screen back.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ui.caret import tokens
from ui.caret.caret import Caret
from ui.caret.text import Machine, Prose
from ui.home import motion


class InvokeLine(QWidget):
    """The summoned line."""

    message_submitted = Signal(str)
    expand_requested = Signal()
    cancel_requested = Signal()

    WIDTH = 560

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._build()

        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(1 if motion.reduced_motion() else 155)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self.hide()

    # ── Build ────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._shell = QFrame()
        self._shell.setObjectName("invoke")
        self._shell.setStyleSheet(
            f"""
            QFrame#invoke {{
                background: {tokens.SURFACE};
                border: 1px solid {tokens.HAIRLINE_LIT};
                border-radius: 5px;
            }}
            """
        )

        column = QVBoxLayout(self._shell)
        column.setContentsMargins(17, 15, 18, 15)
        column.setSpacing(0)

        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(12)

        self.caret = Caret(4, 17)
        self.caret.set_state("responding")
        line.addWidget(self.caret, 0, Qt.AlignVCenter)

        self.field = QLineEdit()
        self.field.setPlaceholderText("Ask, or just talk")
        self.field.setFont(tokens.prose(15))
        self.field.setFrame(False)
        self.field.returnPressed.connect(self._submit)
        self.field.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent; border: none;
                color: {tokens.TEXT};
                selection-background-color: {tokens.HAIRLINE_LIT};
                padding: 0;
            }}
            QLineEdit::placeholder {{ color: {tokens.MUTED}; }}
            """
        )
        line.addWidget(self.field, 1)

        self._keys = QLabel("⌘⇧space")
        self._keys.setFont(tokens.machine(11))
        self._keys.setStyleSheet(
            f"color: {tokens.FAINT}; background: transparent; border: none;"
        )
        line.addWidget(self._keys, 0, Qt.AlignVCenter)

        column.addLayout(line)

        # Everything below appears only when there is something real in it,
        # indented to the same gutter the caret occupies so the line and the
        # answer share one spine.
        self._answer = QFrame()
        self._answer.setObjectName("answer")
        self._answer.setStyleSheet(
            f"QFrame#answer {{ background: transparent; border: none;"
            f" border-top: 1px solid {tokens.HAIRLINE}; }}"
        )
        answer = QVBoxLayout(self._answer)
        answer.setContentsMargins(16, 14, 0, 0)
        answer.setSpacing(9)

        self._did = Machine("", size=11)
        self._did.hide()
        answer.addWidget(self._did)

        self._said = Prose("", size=14)
        self._said.hide()
        answer.addWidget(self._said)

        self._answer_gap = self._answer      # kept: the controller-facing name
        self._answer.hide()
        column.addSpacing(0)
        column.addWidget(self._answer)

        root.addWidget(self._shell)

    # ── Geometry ─────────────────────────────────────────

    def _place(self, animate_open: bool = False) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()

        self._shell.adjustSize()
        height = max(52, self._shell.sizeHint().height())
        x = geo.center().x() - self.WIDTH // 2
        y = geo.top() + int(geo.height() * 0.26)

        target = QRect(x, y, self.WIDTH, height)

        if animate_open and not motion.reduced_motion():
            self.setGeometry(
                QRect(geo.center().x() - 12, y, 24, height)
            )
            self._anim.stop()
            self._anim.setStartValue(self.geometry())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.setGeometry(target)

    def _resize_to_content(self) -> None:
        QTimer.singleShot(0, lambda: self._place(animate_open=False))

    # ── Controller contract ──────────────────────────────

    def activate(self, start_listening: bool = False) -> None:
        self.clear_response()
        self.field.clear()

        was_hidden = not self.isVisible()
        self.show()
        self.raise_()
        self.activateWindow()
        self.field.setFocus()

        self._place(animate_open=was_hidden)

        if start_listening:
            self.caret.set_state("listening")

    def dismiss(self) -> None:
        self.hide()
        self.clear_response()
        self.caret.set_state("responding")

    def set_state(self, state: str, status: str = "") -> None:
        mapped = {
            "thinking": "thinking",
            "listening": "listening",
            "transcribing": "thinking",
            "working": "working",
            "speaking": "responding",
            "needs_user": "needs_user",
            "error": "error",
        }.get(state, "idle")
        self.caret.set_state(mapped)

        if status:
            self._show_did(status)

    def show_tool_status(self, text: str) -> None:
        self.caret.set_state("working")
        self._show_did(text)

    def show_tool_done(self, text: str, success: bool = True) -> None:
        self._did.set_colour(tokens.FAINT if success else tokens.RED)

    def set_response(self, text: str) -> None:
        self._said.set_text(text)
        self._said.show()
        self._answer_gap.show()
        self._resize_to_content()

    def append_response(self, token: str) -> None:
        if not self._said.isVisible():
            self._said.show()
            self._answer_gap.show()
        self._said.append_text(token)
        self._resize_to_content()

    def clear_response(self) -> None:
        self._said.set_text("")
        self._said.hide()
        self._did.set_text("")
        self._did.hide()
        self._answer_gap.hide()
        self._resize_to_content()

    def finish(self) -> None:
        self.caret.set_state("idle")

    def _show_did(self, text: str) -> None:
        self._did.set_colour(tokens.DIM)
        self._did.set_text(" ".join(text.split())[:88])
        self._did.show()
        self._answer_gap.show()
        self._resize_to_content()

    # ── Interaction ──────────────────────────────────────

    def _submit(self) -> None:
        text = self.field.text().strip()
        if text:
            self.field.clear()
            self.message_submitted.emit(text)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.cancel_requested.emit()
            self.dismiss()
            return
        if event.key() == Qt.Key_Down and event.modifiers() & Qt.ShiftModifier:
            self.expand_requested.emit()
            return
        super().keyPressEvent(event)
