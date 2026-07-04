from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
)

from ui.widgets.header import Header
from ui.widgets.conversation import ConversationPanel
from ui.widgets.input import InputBar


class ChatPage(QWidget):
    """
    Mike Main Workspace.

    Layout
    ------
    Header
        ↓
    Conversation
        ↓
    Composer

    Presentation layer only.
    """

    COMPOSER_WIDTH = 1180

    # =====================================================

    def __init__(self) -> None:

        super().__init__()

        self._build_ui()

    # =====================================================

    def _build_ui(self) -> None:

        root = QVBoxLayout(self)

        root.setContentsMargins(
            0,
            0,
            0,
            20,
        )

        root.setSpacing(12)

        # -------------------------------------------------
        # Header
        # -------------------------------------------------

        self.header = Header()

        root.addWidget(
            self.header
        )

        # -------------------------------------------------
        # Conversation
        # -------------------------------------------------

        self.conversation = ConversationPanel()

        root.addWidget(
            self.conversation,
            1,
        )

        # -------------------------------------------------
        # Composer
        # -------------------------------------------------

        self.input = InputBar()

        self.input.setMaximumWidth(
            self.COMPOSER_WIDTH
        )

        root.addWidget(
            self.input,
            0,
            Qt.AlignHCenter,
        )

    # =====================================================
    # Conversation API
    # =====================================================

    def add_user_message(
        self,
        text: str,
    ) -> None:

        self.conversation.add_user(
            text
        )

    # -----------------------------------------------------

    def add_mike_message(
        self,
        text: str,
    ) -> None:

        self.conversation.add_mike(
            text
        )

    # -----------------------------------------------------

    def show_thinking(
        self,
    ) -> None:

        self.conversation.show_thinking()

    # -----------------------------------------------------

    def hide_thinking(
        self,
    ) -> None:

        self.conversation.hide_thinking()

    # -----------------------------------------------------

    def clear(
        self,
    ) -> None:

        self.conversation.clear()