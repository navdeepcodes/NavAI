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

    COMPOSER_WIDTH = 800

    def __init__(self) -> None:

        super().__init__()

        self._build_ui()

    def _build_ui(self) -> None:

        root = QVBoxLayout(self)

        root.setContentsMargins(0, 0, 0, 0)

        root.setSpacing(0)

        # Header

        self.header = Header()

        root.addWidget(self.header)

        # Conversation

        self.conversation = ConversationPanel()

        root.addWidget(self.conversation, 1)

        # Input

        self.input = InputBar()

        self.input.setMaximumWidth(self.COMPOSER_WIDTH)

        root.addWidget(
            self.input,
            0,
            Qt.AlignHCenter,
        )

    # Conversation API

    def add_user_message(self, text: str) -> None:

        self.conversation.add_user(text)

        self.input.hide_hint()

    def add_mike_message(self, text: str) -> None:

        self.conversation.add_mike(text)

    def begin_mike_stream(self):

        return self.conversation.begin_mike_stream()

    def add_action_card(self, text: str):

        return self.conversation.add_action_card(text)

    def show_tool_status(self, text: str) -> None:

        self.conversation.show_tool(text)

    def show_thinking(self) -> None:

        self.header.thinking()

        self.conversation.show_thinking()

    def hide_thinking(self) -> None:

        self.header.ready()

        self.conversation.hide_thinking()

    def clear(self) -> None:

        self.conversation.clear()

        self.input.show_hint()
