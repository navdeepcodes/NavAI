from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from ui.widgets.conversation.chat_message import ChatMessage


class BubbleBase(QFrame):
    """
    Base class for every conversation bubble.

    All message widgets inherit from this class.

    Responsibilities
    ----------------
    • Consistent layout
    • Title
    • Message text
    • Timestamp
    • OLED styling
    • Left / Right alignment

    Future
    ------
    • Markdown
    • Code blocks
    • Copy button
    • Streaming cursor
    • Hover animations
    """

    MAX_WIDTH = 720

    # -----------------------------------------------------

    def __init__(
        self,
        message: ChatMessage,
    ) -> None:

        super().__init__()

        self.message = message

        self._build_ui()

    # -----------------------------------------------------

    def _build_ui(self) -> None:

        outer = QHBoxLayout(self)

        outer.setContentsMargins(18, 8, 18, 8)

        outer.setSpacing(0)

        self.card = QFrame()

        self.card.setMaximumWidth(
            self.MAX_WIDTH
        )

        self.card.setObjectName(
            "bubble"
        )

        body = QVBoxLayout(
            self.card
        )

        body.setContentsMargins(
            18,
            14,
            18,
            14,
        )

        body.setSpacing(8)

        # ------------------------------------------

        self.title = QLabel()

        title_font = QFont()

        title_font.setBold(True)

        title_font.setPointSize(10)

        self.title.setFont(
            title_font
        )

        body.addWidget(
            self.title
        )

        # ------------------------------------------

        self.content = QLabel(
            self.message.text
        )

        self.content.setWordWrap(
            True
        )

        self.content.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        font = QFont()

        font.setPointSize(11)

        self.content.setFont(
            font
        )

        body.addWidget(
            self.content
        )

        # ------------------------------------------

        self.timestamp = QLabel(
            self.message.timestamp.strftime(
                "%H:%M"
            )
        )

        self.timestamp.setAlignment(
            Qt.AlignRight
        )

        self.timestamp.setObjectName(
            "timestamp"
        )

        body.addWidget(
            self.timestamp
        )

        self._apply_theme()

        if self.message.is_user:

            outer.addStretch()

            outer.addWidget(
                self.card
            )

        else:

            outer.addWidget(
                self.card
            )

            outer.addStretch()

    # -----------------------------------------------------

    def _apply_theme(self) -> None:

        if self.message.is_user:

            border = "#2563eb"

            background = "#08131f"

            title = "#60a5fa"

        elif self.message.is_assistant:

            border = "#262626"

            background = "#101010"

            title = "#10b981"

        elif self.message.is_system:

            border = "#404040"

            background = "#0b0b0b"

            title = "#9ca3af"

        elif self.message.is_tool:

            border = "#0ea5e9"

            background = "#07131a"

            title = "#38bdf8"

        elif self.message.is_planner:

            border = "#f59e0b"

            background = "#161109"

            title = "#fbbf24"

        elif self.message.is_thinking:

            border = "#525252"

            background = "#0d0d0d"

            title = "#a3a3a3"

        else:

            border = "#dc2626"

            background = "#1a0d0d"

            title = "#ef4444"

        self.card.setStyleSheet(
            f"""
            QFrame#bubble{{
                background:{background};
                border:1px solid {border};
                border-radius:16px;
            }}

            QLabel{{
                background:transparent;
                color:#f5f5f5;
            }}

            QLabel#timestamp{{
                color:#666666;
                font-size:10px;
            }}
            """
        )

        self.title.setStyleSheet(
            f"""
            color:{title};
            letter-spacing:0.4px;
            """
        )

    # -----------------------------------------------------

    def set_title(
        self,
        text: str,
    ) -> None:

        self.title.setText(
            text
        )

    # -----------------------------------------------------

    def set_text(
        self,
        text: str,
    ) -> None:

        self.message.text = text

        self.content.setText(
            text
        )

    # -----------------------------------------------------

    def append(
        self,
        token: str,
    ) -> None:

        self.message.append(
            token
        )

        self.content.setText(
            self.message.text
        )