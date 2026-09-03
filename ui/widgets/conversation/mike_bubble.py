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
from ui.widgets.conversation.markdown import md_to_html


class MikeBubble(QFrame):

    MIN_WIDTH = 360
    MAX_WIDTH = 680

    def __init__(self, text: str) -> None:

        super().__init__()

        self._raw = text

        self.setObjectName("mike_bubble")

        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self.MAX_WIDTH)

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(0)

        self.content = QLabel()
        self.content.setObjectName("content")
        self.content.setWordWrap(True)
        self.content.setTextFormat(Qt.RichText)
        self.content.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        if text:
            self.content.setText(md_to_html(text))

        layout.addWidget(self.content)

        self._apply_style()

    def _apply_style(self) -> None:

        self.setStyleSheet(
            f"""
            QFrame#mike_bubble {{
                background: {colors.SURFACE};
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
        self._raw = text
        self.content.setText(md_to_html(text))

    def append_text(self, text: str) -> None:
        self._raw += text
        self.content.setText(md_to_html(self._raw))

    def text(self) -> str:
        return self._raw
