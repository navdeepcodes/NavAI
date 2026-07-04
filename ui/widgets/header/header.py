from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
)

from ui.theme import colors
from ui.theme import spacing
from ui.theme import typography


class Header(QFrame):
    """
    Mike application header.

    Displays only:
    • Application name
    • Runtime state

    Presentation only.
    """

    HEADER_HEIGHT = 56

    # =====================================================

    def __init__(self) -> None:

        super().__init__()

        self._build_ui()

        self._apply_theme()

    # =====================================================

    def _build_ui(self) -> None:

        self.setFixedHeight(self.HEADER_HEIGHT)

        layout = QHBoxLayout(self)

        layout.setContentsMargins(
            28,
            0,
            28,
            0,
        )

        layout.setSpacing(12)

        # -------------------------------------------------

        self.title = QLabel("Mike")

        self.title.setObjectName(
            "title"
        )

        layout.addWidget(
            self.title
        )

        layout.addStretch()

        # -------------------------------------------------

        self.state = QLabel("Ready")

        self.state.setObjectName(
            "state"
        )

        self.state.setAlignment(
            Qt.AlignRight | Qt.AlignVCenter
        )

        layout.addWidget(
            self.state
        )

    # =====================================================

    def _apply_theme(self) -> None:

        self.setStyleSheet(
            f"""
            Header {{
                background: {colors.WINDOW};
                border-bottom: 1px solid {colors.BORDER};
            }}

            QLabel#title {{
                color: {colors.TEXT};
                font-size: {typography.TITLE}px;
                font-weight: 700;
            }}

            QLabel#state {{
                color: {colors.TEXT_MUTED};
                font-size: {typography.SMALL}px;
                font-weight: 500;
            }}
            """
        )

    # =====================================================
    # Public API
    # =====================================================

    def ready(self) -> None:

        self.state.setText("Ready")

    # -----------------------------------------------------

    def thinking(self) -> None:

        self.state.setText("Thinking...")

    # -----------------------------------------------------

    def error(self) -> None:

        self.state.setText("Error")

    # -----------------------------------------------------

    def set_state(
        self,
        text: str,
    ) -> None:

        self.state.setText(text)