from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
)

from ui.theme import colors


# ==========================================================
# Command Input
# ==========================================================


class CommandInput(QTextEdit):

    submitted = Signal(str)

    MIN_HEIGHT = 44
    MAX_HEIGHT = 120

    def __init__(self) -> None:

        super().__init__()

        self._build()

    # -----------------------------------------------------

    def _build(self) -> None:

        self.setPlaceholderText(
            "Message Mike..."
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

        self.setFrameShape(
            QFrame.NoFrame
        )

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        self.setFixedHeight(
            self.MIN_HEIGHT
        )

        self.textChanged.connect(
            self._resize
        )

        # Fix oversized first render
        QTimer.singleShot(
            0,
            self._resize,
        )

    # -----------------------------------------------------

    def keyPressEvent(
        self,
        event,
    ) -> None:

        if (
            event.key()
            in (
                Qt.Key_Return,
                Qt.Key_Enter,
            )
            and not (
                event.modifiers()
                & Qt.ShiftModifier
            )
        ):

            text = self.toPlainText().strip()

            if text:

                self.submitted.emit(
                    text
                )

                self.clear()

            return

        super().keyPressEvent(event)

    # -----------------------------------------------------

    def _resize(self) -> None:

        document_height = (
            self.document()
            .documentLayout()
            .documentSize()
            .height()
        )

        height = int(document_height) + 12

        height = max(
            self.MIN_HEIGHT,
            min(
                self.MAX_HEIGHT,
                height,
            ),
        )

        self.setFixedHeight(
            height
        )


# ==========================================================
# Input Bar
# ==========================================================


class InputBar(QFrame):

    submitted = Signal(str)

    BUTTON_SIZE = 36

    def __init__(self) -> None:

        super().__init__()

        self._build()

        self._theme()

    # -----------------------------------------------------

    def _build(self) -> None:

        outer = QVBoxLayout(self)

        outer.setContentsMargins(
            32,
            12,
            32,
            18,
        )

        outer.setSpacing(0)

        self.composer = QFrame()

        self.composer.setObjectName(
            "composer"
        )

        layout = QHBoxLayout(
            self.composer
        )

        layout.setContentsMargins(
            14,
            8,
            14,
            8,
        )

        layout.setSpacing(8)

        style = QApplication.style()

        # -------------------------------------------------
        # Attachment
        # -------------------------------------------------

        self.attach = QPushButton()

        self.attach.setIcon(
            style.standardIcon(
                QStyle.SP_FileIcon
            )
        )

        self.attach.setFixedSize(
            self.BUTTON_SIZE,
            self.BUTTON_SIZE,
        )

        # -------------------------------------------------
        # Input
        # -------------------------------------------------

        self.input = CommandInput()

        self.input.submitted.connect(
            self.submitted.emit
        )

        # -------------------------------------------------
        # Voice
        # -------------------------------------------------

        self.voice = QPushButton("●")

        self.voice.setFixedSize(
            self.BUTTON_SIZE,
            self.BUTTON_SIZE,
        )

        # -------------------------------------------------
        # Send
        # -------------------------------------------------

        self.send = QPushButton()

        self.send.setIcon(
            style.standardIcon(
                QStyle.SP_ArrowForward
            )
        )

        self.send.setFixedSize(
            self.BUTTON_SIZE,
            self.BUTTON_SIZE,
        )

        self.send.clicked.connect(
            self._submit
        )

        layout.addWidget(
            self.attach
        )

        layout.addWidget(
            self.input,
            1,
        )

        layout.addWidget(
            self.voice
        )

        layout.addWidget(
            self.send
        )

        outer.addWidget(
            self.composer
        )

    # -----------------------------------------------------

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
                border-radius: 22px;
            }}

            QTextEdit {{
                background: transparent;
                border: none;
                color: {colors.TEXT};
                font-size: 15px;
                padding: 2px 4px;
            }}

            QTextEdit:focus {{
                border: none;
            }}

            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 18px;
                color: {colors.TEXT};
                font-size: 15px;
            }}

            QPushButton:hover {{
                background: {colors.HOVER};
            }}

            QPushButton:pressed {{
                background: {colors.HOVER};
            }}
            """
        )

    # -----------------------------------------------------

    def _submit(self) -> None:

        text = self.text().strip()

        if not text:

            return

        self.submitted.emit(
            text
        )

        self.clear()

    # =====================================================
    # Public API
    # =====================================================

    def text(self) -> str:

        return self.input.toPlainText()

    # -----------------------------------------------------

    def clear(self) -> None:

        self.input.clear()

        self.input.setFixedHeight(
            self.input.MIN_HEIGHT
        )

    # -----------------------------------------------------

    def focus(self) -> None:

        self.input.setFocus(
            Qt.OtherFocusReason
        )

    # -----------------------------------------------------

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:

        self.input.setEnabled(
            enabled
        )

        self.attach.setEnabled(
            enabled
        )

        self.voice.setEnabled(
            enabled
        )

        self.send.setEnabled(
            enabled
        )