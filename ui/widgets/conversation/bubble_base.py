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


class BubbleBase(QFrame):

    MAX_WIDTH = 640

    def __init__(
        self,
        *,
        text: str,
        show_header: bool = False,
        header_text: str = "",
    ) -> None:

        super().__init__()

        self.setObjectName("bubble")

        self.setMaximumWidth(self.MAX_WIDTH)

        self.setSizePolicy(
            QSizePolicy.Maximum,
            QSizePolicy.Fixed,
        )

        self._build_ui(text, show_header, header_text)

    def _build_ui(
        self,
        text: str,
        show_header: bool,
        header_text: str,
    ) -> None:

        layout = QVBoxLayout(self)

        layout.setContentsMargins(16, 12, 16, 12)

        layout.setSpacing(6)

        self.header = QLabel(header_text)
        self.header.setObjectName("header")

        if not show_header:
            self.header.hide()

        self.content = QLabel(text)
        self.content.setObjectName("content")
        self.content.setWordWrap(True)

        self.content.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        layout.addWidget(self.header)
        layout.addWidget(self.content)

    # Public API

    def set_text(self, text: str) -> None:

        self.content.setText(text)

    def append_text(self, text: str) -> None:

        self.content.setText(
            self.content.text() + text
        )

    def text(self) -> str:

        return self.content.text()
