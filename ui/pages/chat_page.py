from __future__ import annotations

from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

from ui.widgets.conversation import ConversationPanel
from ui.widgets.header import Header
from ui.widgets.input_bar import InputBar
from ui.widgets.status_bar import StatusBar


class ChatPage(QWidget):
    """
    Main chat workspace.

    Presentation layer only.

    Owns:
        • Header
        • Conversation
        • Input
        • Status Bar

    Contains no runtime or business logic.
    """

    # =====================================================

    def __init__(self) -> None:

        super().__init__()

        self._build_ui()

    # =====================================================

    def _build_ui(self) -> None:

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout.setSpacing(0)

        # -------------------------------------------------
        # Header
        # -------------------------------------------------

        self.header = Header()

        layout.addWidget(
            self.header
        )

        # -------------------------------------------------
        # Conversation
        # -------------------------------------------------

        self.conversation = ConversationPanel()

        layout.addWidget(
            self.conversation,
            stretch=1,
        )

        # -------------------------------------------------
        # Input
        # -------------------------------------------------

        self.input = InputBar()

        layout.addWidget(
            self.input
        )

        # -------------------------------------------------
        # Status
        # -------------------------------------------------

        self.status = StatusBar()

        layout.addWidget(
            self.status
        )

    # =====================================================
    # Public API
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

    def clear(self) -> None:

        self.conversation.clear()