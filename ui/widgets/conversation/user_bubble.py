from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from ui.theme import colors
from ui.theme import typography


class UserBubble(QFrame):

    MAX_WIDTH = 520
    MIN_WIDTH = 60

    def __init__(self, text: str) -> None:

        super().__init__()

        self.setObjectName("user_bubble")

        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self.MAX_WIDTH)

        self.setSizePolicy(
            QSizePolicy.Maximum,
            QSizePolicy.Preferred,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(0)

        self.content = QLabel(text)
        self.content.setObjectName("content")
        self.content.setWordWrap(True)
        self.content.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        layout.addWidget(self.content)

        self.setStyleSheet(
            f"""
            QFrame#user_bubble {{
                background: #1E2D4A;
                border: none;
                border-radius: 18px;
            }}

            QLabel#content {{
                background: transparent;
                color: {colors.TEXT};
                font-size: {typography.BODY}px;
                border: none;
            }}
            """
        )

    def set_text(self, text: str) -> None:
        self.content.setText(text)

    def append_text(self, text: str) -> None:
        self.content.setText(self.content.text() + text)

    def text(self) -> str:
        return self.content.text()
