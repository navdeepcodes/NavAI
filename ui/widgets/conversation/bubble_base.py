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
    """
    Base conversation bubble.

    Shared by every message type.

    Responsibilities
    ----------------
    • Bubble layout
    • Typography
    • Padding
    • Maximum width

    Colour is supplied by subclasses.
    """

    MAX_WIDTH = 620

    # =====================================================

    def __init__(
        self,
        *,
        title: str,
        text: str,
    ) -> None:

        super().__init__()

        self.setObjectName("bubble")

        self.setMaximumWidth(self.MAX_WIDTH)

        self.setSizePolicy(
            QSizePolicy.Maximum,
            QSizePolicy.Fixed,
        )

        self._build_ui(
            title,
            text,
        )

        self._apply_theme()

    # =====================================================

    def _build_ui(
        self,
        title: str,
        text: str,
    ) -> None:

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            18,
            14,
            18,
            14,
        )

        layout.setSpacing(8)

        self.header = QLabel(title.upper())

        self.header.setObjectName(
            "header"
        )

        self.content = QLabel(text)

        self.content.setObjectName(
            "content"
        )

        self.content.setWordWrap(True)

        self.content.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        layout.addWidget(self.header)

        layout.addWidget(self.content)

    # =====================================================

    def _apply_theme(self) -> None:

        self.setStyleSheet(
            f"""
            QFrame#bubble {{

                background: {colors.SURFACE};
                border: none;
                border-radius: 18px;

            }}

            QLabel {{

                background: transparent;
                border: none;

            }}

            QLabel#header {{

                color: {colors.TEXT_MUTED};
                font-size: {typography.TINY}px;
                font-weight: 700;
                letter-spacing: 1px;

            }}

            QLabel#content {{

                color: {colors.TEXT};
                font-size: {typography.BODY}px;
                font-weight: 400;

            }}
            """
        )

    # =====================================================
    # Public API
    # =====================================================

    def set_text(
        self,
        text: str,
    ) -> None:

        self.content.setText(text)

    # -----------------------------------------------------

    def append_text(
        self,
        text: str,
    ) -> None:

        self.content.setText(
            self.content.text() + text
        )

    # -----------------------------------------------------

    def text(self) -> str:

        return self.content.text()