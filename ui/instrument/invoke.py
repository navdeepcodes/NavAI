"""D2 — invocation. Summoned deliberately, so it may take focus.

⌘⇧Space or the wake word from anywhere. One brass-edged instrument window,
a dial standing in for the mic/send icon, a single line to type into.
"""
from __future__ import annotations

import random

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ui.home import motion
from ui.instrument import tokens
from ui.instrument.aura import Aura
from ui.instrument.dial import Dial
from ui.instrument.widgets import EngravedLabel, InkFact

# A short, honest greeting on each fresh summon — rotated so it never reads
# as a canned line you've memorized by the tenth time you see it.
GREETINGS = (
    "How can I help?",
    "At your service.",
    "Ready when you are.",
    "What are we doing?",
    "Go ahead.",
)


class InvokeLine(QWidget):

    message_submitted = Signal(str)
    expand_requested = Signal()
    cancel_requested = Signal()

    WIDTH = 540
    BOTTOM_MARGIN = 64

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._aura = Aura()
        self._build()

        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(1 if motion.reduced_motion() else 170)
        self._anim.setEasingCurve(QEasingCurve.OutBack)
        self.hide()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._shell = QFrame()
        self._shell.setObjectName("invoke")
        self._shell.setStyleSheet(
            f"""
            QFrame#invoke {{
                background: {tokens.PANEL};
                border: 1px solid {tokens.BEZEL};
                border-radius: 8px;
            }}
            """
        )
        col = QVBoxLayout(self._shell)
        col.setContentsMargins(18, 15, 18, 15)
        col.setSpacing(0)

        line = QHBoxLayout()
        line.setSpacing(13)
        self.dial = Dial(28)
        line.addWidget(self.dial, 0, Qt.AlignVCenter)

        self.field = QLineEdit()
        self.field.setPlaceholderText("Ask, or just talk")
        self.field.setFont(tokens.sans(15))
        self.field.setFrame(False)
        self.field.returnPressed.connect(self._submit)
        self.field.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent; border: none; color: {tokens.TEXT};
                selection-background-color: {tokens.HAIRLINE}; padding: 0;
            }}
            """
        )
        line.addWidget(self.field, 1)

        self._keys = EngravedLabel("⌘⇧space", colour=tokens.FAINT, size=10)
        line.addWidget(self._keys, 0, Qt.AlignVCenter)
        col.addLayout(line)

        self._answer = QFrame()
        self._answer.setStyleSheet(f"border: none; border-top: 1px solid {tokens.HAIRLINE};")
        ans = QVBoxLayout(self._answer)
        ans.setContentsMargins(41, 12, 0, 0)
        ans.setSpacing(8)
        self._did = InkFact("")
        self._did.hide()
        ans.addWidget(self._did)
        self._said = EngravedLabel("", colour=tokens.TEXT, size=13)
        self._said.setWordWrap(True)
        self._said.hide()
        ans.addWidget(self._said)
        self._answer.hide()
        col.addWidget(self._answer)

        root.addWidget(self._shell)

    def _place(self, animate_open: bool = False) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        # availableGeometry already excludes the menu bar and, when visible,
        # the Dock — so anchoring to its bottom edge sits just above the Dock
        # rather than needing a guessed margin for it.
        geo = screen.availableGeometry()
        self._shell.adjustSize()
        height = max(56, self._shell.sizeHint().height())
        x = geo.center().x() - self.WIDTH // 2
        # Anchored to the bottom, growing upward: as the answer appears below
        # the line and the box grows taller, its bottom edge stays put rather
        # than pushing the box down toward — or under — the Dock.
        y = geo.bottom() - self.BOTTOM_MARGIN - height
        target = QRect(x, y, self.WIDTH, height)

        if animate_open and not motion.reduced_motion():
            self.setGeometry(QRect(geo.center().x() - 14, y, 28, height))
            self._anim.stop()
            self._anim.setStartValue(self.geometry())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.setGeometry(target)

    def _resize_to_content(self) -> None:
        QTimer.singleShot(0, lambda: self._place(animate_open=False))

    def activate(self, start_listening: bool = False) -> None:
        self.clear_response()
        self.field.clear()
        was_hidden = not self.isVisible()
        if was_hidden:
            # A fresh summon gets a fresh greeting; re-focusing an already
            # open line mid-thought shouldn't swap the text under you.
            self.field.setPlaceholderText(random.choice(GREETINGS))
        self._aura.pulse()
        self.show()
        self.raise_()
        self.activateWindow()
        self.field.setFocus()
        self._place(animate_open=was_hidden)
        if start_listening:
            self.dial.set_state("listening")

    def dismiss(self) -> None:
        self.hide()
        self.clear_response()
        self.dial.set_state("idle")
        self._aura.release()

    def set_state(self, state: str, status: str = "") -> None:
        mapped = {
            "thinking": "thinking", "listening": "listening", "transcribing": "thinking",
            "working": "working", "speaking": "responding", "needs_user": "needs_user", "error": "error",
        }.get(state, "idle")
        self.dial.set_state(mapped)
        if status:
            self._show_did(status)

    def show_tool_status(self, text: str) -> None:
        self.dial.set_state("working")
        self._show_did(text)

    def show_tool_done(self, text: str, success: bool = True) -> None:
        self._did.set_text(getattr(self, "_last_did", ""))

    def set_response(self, text: str) -> None:
        self._said.set_text(text)
        self._said.show()
        self._answer.show()
        self._resize_to_content()

    def append_response(self, token: str) -> None:
        if not self._said.isVisible():
            self._said.show()
            self._answer.show()
        current = self._said.text()
        self._said.set_text(current + token)
        self._resize_to_content()

    def clear_response(self) -> None:
        self._said.set_text("")
        self._said.hide()
        self._did.set_text("")
        self._did.hide()
        self._answer.hide()
        self._resize_to_content()

    def finish(self) -> None:
        self.dial.set_state("idle")
        self._aura.release()

    def _show_did(self, text: str) -> None:
        self._last_did = " ".join(text.split())[:88]
        self._did.set_text(self._last_did)
        self._did.show()
        self._answer.show()
        self._resize_to_content()

    def _submit(self) -> None:
        text = self.field.text().strip()
        if text:
            self.field.clear()
            # Covers a follow-up typed while the line is still open from the
            # last answer — pulse() is a no-op if the aura never faded, but
            # if finish() already released it, this relights it for the new
            # exchange rather than leaving it dark while Mike works.
            self._aura.pulse()
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
