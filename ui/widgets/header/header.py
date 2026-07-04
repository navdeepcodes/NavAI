from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)

from ui.theme import colors, fonts
from ui.widgets.thinking_indicator import (
    ThinkingIndicator,
    ThinkingState,
)


class Header(QFrame):
    """
    Mike application header.

    Layout

    MIKE                    ◉ Ready                    ☰
    """

    # ---------------------------------------------------------

    def __init__(self):

        super().__init__()

        self._build_ui()

    # ---------------------------------------------------------

    def _build_ui(self):

        self.setFixedHeight(64)

        self.setStyleSheet(
            f"""
            QFrame {{
                background: {colors.BACKGROUND};
                border: none;
                border-bottom: 1px solid {colors.BORDER};
            }}
            """
        )

        layout = QHBoxLayout(self)

        layout.setContentsMargins(28, 0, 28, 0)

        layout.setSpacing(16)

        # -------------------------------------------------
        # Title
        # -------------------------------------------------

        self.title = QLabel("MIKE")

        self.title.setFont(fonts.TITLE)

        self.title.setStyleSheet(
            f"""
            color: {colors.TEXT};
            letter-spacing: 2px;
            """
        )

        layout.addWidget(self.title)

        # -------------------------------------------------
        # Spacer
        # -------------------------------------------------

        spacer = QLabel()

        spacer.setSizePolicy(

            QSizePolicy.Expanding,

            QSizePolicy.Preferred,

        )

        layout.addWidget(spacer)

        # -------------------------------------------------
        # Status
        # -------------------------------------------------

        status_layout = QHBoxLayout()

        status_layout.setSpacing(8)

        self.indicator = ThinkingIndicator()

        status_layout.addWidget(

            self.indicator,

            alignment=Qt.AlignVCenter,

        )

        self.status = QLabel("Ready")

        self.status.setFont(fonts.STATUS)

        self.status.setStyleSheet(
            f"""
            color: {colors.TEXT_SECONDARY};
            """
        )

        status_layout.addWidget(

            self.status,

            alignment=Qt.AlignVCenter,

        )

        layout.addLayout(status_layout)

        # -------------------------------------------------
        # Menu
        # -------------------------------------------------

        self.menu = QPushButton("☰")

        self.menu.setCursor(Qt.PointingHandCursor)

        self.menu.setFixedSize(32, 32)

        self.menu.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {colors.TEXT_SECONDARY};
                font-size: 18px;
            }}

            QPushButton:hover {{
                color: {colors.TEXT};
            }}

            QPushButton:pressed {{
                color: {colors.ACCENT};
            }}
            """
        )

        layout.addWidget(self.menu)

        self.set_state(

            ThinkingState.IDLE

        )

    # ---------------------------------------------------------

    def set_state(

        self,

        state: ThinkingState,

    ):

        labels = {

            ThinkingState.IDLE: "Ready",

            ThinkingState.THINKING: "Thinking",

            ThinkingState.EXECUTING: "Executing",

            ThinkingState.LOCAL: "Local",

            ThinkingState.LISTENING: "Listening",

        }

        self.status.setText(

            labels[state]

        )

        self.indicator.set_state(

            state

        )

    # ---------------------------------------------------------

    def set_title(

        self,

        title: str,

    ):

        self.title.setText(

            title.upper()

        )