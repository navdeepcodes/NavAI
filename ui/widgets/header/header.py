from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
)

from ui.theme import colors
from ui.widgets.floating.presence import PresenceIndicator


class Header(QFrame):

    HEADER_HEIGHT = 52

    def __init__(self) -> None:

        super().__init__()
        self._build_ui()
        self._apply_theme()

    def _build_ui(self) -> None:

        self.setFixedHeight(self.HEADER_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 28, 0)
        layout.setSpacing(8)

        self._presence = PresenceIndicator(self)
        layout.addWidget(self._presence)

        self.title = QLabel("Mike")
        self.title.setObjectName("title")
        layout.addWidget(self.title)

        layout.addStretch()

    def _apply_theme(self) -> None:

        self.setStyleSheet(
            f"""
            Header {{
                background: {colors.WINDOW};
                border-bottom: 1px solid {colors.BORDER_SUBTLE};
            }}

            QLabel#title {{
                color: {colors.TEXT};
                font-size: 16px;
                font-weight: 600;
                letter-spacing: -0.3px;
            }}
            """
        )

    def ready(self) -> None:
        self._presence.set_state("idle")

    def thinking(self) -> None:
        self._presence.set_state("thinking")

    def error(self) -> None:
        self._presence.set_state("idle")

    def set_state(self, state: str) -> None:
        self._presence.set_state(state)
