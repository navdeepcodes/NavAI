from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)

from ui.theme import colors
from ui.theme import typography
from ui.widgets.input.voice_button import VoiceButton


# ==========================================================
# Command Input
# ==========================================================


class CommandInput(QTextEdit):

    submitted = Signal(str)

    MIN_HEIGHT = 44
    MAX_HEIGHT = 140

    def __init__(self) -> None:

        super().__init__()

        self._build()

    def _build(self) -> None:

        self.setPlaceholderText(
            "Ask Mike to do something..."
        )

        self.setAcceptRichText(False)

        self.setWordWrapMode(
            QTextOption.WrapAtWordBoundaryOrAnywhere
        )

        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        self.setFrameShape(QFrame.NoFrame)

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        self.setFixedHeight(self.MIN_HEIGHT)

        self.textChanged.connect(self._resize)

        QTimer.singleShot(0, self._resize)

    def keyPressEvent(self, event) -> None:

        if (
            event.key()
            in (Qt.Key_Return, Qt.Key_Enter)
            and not (event.modifiers() & Qt.ShiftModifier)
        ):
            text = self.toPlainText().strip()

            if text:
                self.submitted.emit(text)
                self.clear()

            return

        super().keyPressEvent(event)

    def _resize(self) -> None:

        doc_height = (
            self.document()
            .documentLayout()
            .documentSize()
            .height()
        )

        height = int(doc_height) + 12

        height = max(
            self.MIN_HEIGHT,
            min(self.MAX_HEIGHT, height),
        )

        self.setFixedHeight(height)


# ==========================================================
# Input Bar
# ==========================================================


class InputBar(QFrame):

    submitted = Signal(str)

    def __init__(self) -> None:

        super().__init__()

        self._build()

        self._theme()

    def _build(self) -> None:

        outer = QVBoxLayout(self)

        outer.setContentsMargins(0, 8, 0, 16)

        outer.setSpacing(6)

        # Composer frame

        self.composer = QFrame()
        self.composer.setObjectName("composer")

        layout = QHBoxLayout(self.composer)

        layout.setContentsMargins(16, 6, 10, 6)

        layout.setSpacing(8)

        # Input

        self.input = CommandInput()

        self.input.submitted.connect(
            self.submitted.emit
        )

        layout.addWidget(self.input, 1)

        # Voice button

        self.voice = VoiceButton()

        layout.addWidget(self.voice)

        # Send button

        self.send = QPushButton("↑")
        self.send.setObjectName("send_btn")
        self.send.setFixedSize(32, 32)

        self.send.clicked.connect(self._submit)

        layout.addWidget(self.send)

        outer.addWidget(self.composer)

        # Hint

        self._hint = QLabel(
            "Mike can use your browser, files, and terminal."
        )
        self._hint.setObjectName("hint")
        self._hint.setAlignment(Qt.AlignCenter)

        outer.addWidget(self._hint)

    def _theme(self) -> None:

        self.setStyleSheet(
            f"""
            InputBar {{
                background: transparent;
                border: none;
            }}

            QFrame#composer {{
                background: {colors.SURFACE};
                border: 1px solid {colors.BORDER};
                border-radius: 18px;
            }}

            QFrame#composer:focus-within {{
                border-color: {colors.BORDER_STRONG};
            }}

            QTextEdit {{
                background: transparent;
                border: none;
                color: {colors.TEXT};
                font-size: {typography.BODY}px;
                padding: 4px 2px;
            }}

            QTextEdit:focus {{
                border: none;
            }}

            QPushButton#send_btn {{
                background: {colors.ACCENT};
                border: none;
                border-radius: 16px;
                color: #fff;
                font-size: 16px;
                font-weight: 700;
            }}

            QPushButton#send_btn:hover {{
                background: {colors.ACCENT_DIM};
            }}

            QPushButton#send_btn:disabled {{
                background: {colors.SURFACE_ELEVATED};
                color: {colors.TEXT_DISABLED};
            }}

            QLabel#hint {{
                color: {colors.TEXT_DISABLED};
                font-size: {typography.TINY}px;
                background: transparent;
                border: none;
                padding: 0;
            }}
            """
        )

    def _submit(self) -> None:

        text = self.text().strip()

        if not text:
            return

        self.submitted.emit(text)

        self.clear()

    # Public API

    def text(self) -> str:

        return self.input.toPlainText()

    def clear(self) -> None:

        self.input.clear()

        self.input.setFixedHeight(
            self.input.MIN_HEIGHT
        )

    def focus(self) -> None:

        self.input.setFocus(Qt.OtherFocusReason)

    def set_enabled(self, enabled: bool) -> None:

        self.input.setEnabled(enabled)

        self.send.setEnabled(enabled)

    def hide_hint(self) -> None:

        self._hint.hide()

    def show_hint(self) -> None:

        self._hint.show()
