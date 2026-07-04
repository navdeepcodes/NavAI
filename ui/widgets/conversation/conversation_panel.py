from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.conversation.chat_message import (
    ChatMessage,
    MessageType,
)

from ui.widgets.conversation.message_factory import (
    MessageFactory,
)


class ConversationPanel(QWidget):
    """
    Conversation history.

    Presentation layer only.

    Responsibilities
    ----------------
    • Display conversation
    • Left / right bubble alignment
    • Thinking indicator
    • Auto scrolling
    """

    MAX_CONTENT_WIDTH = 1200
    HORIZONTAL_MARGIN = 20

    # =====================================================

    def __init__(self) -> None:

        super().__init__()

        self._thinking: QWidget | None = None

        self._build_ui()

    # =====================================================

    def _build_ui(self) -> None:

        root = QVBoxLayout(self)

        root.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        root.setSpacing(0)

        # -------------------------------------------------

        self.scroll = QScrollArea()

        self.scroll.setFrameShape(
            QFrame.NoFrame
        )

        self.scroll.setWidgetResizable(
            True
        )

        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        # -------------------------------------------------

        self.container = QWidget()

        self.messages = QVBoxLayout(
            self.container
        )

        self.messages.setContentsMargins(
            0,
            24,
            0,
            24,
        )

        self.messages.setSpacing(
            22
        )

        self.messages.setAlignment(
            Qt.AlignTop
        )

        self.scroll.setWidget(
            self.container
        )

        root.addWidget(
            self.scroll
        )

    # =====================================================

    def _wrap(
        self,
        widget: QWidget,
        *,
        right: bool = False,
    ) -> QWidget:

        wrapper = QWidget()

        wrapper.setMaximumWidth(
            self.MAX_CONTENT_WIDTH
        )

        layout = QHBoxLayout(
            wrapper
        )

        layout.setContentsMargins(
            self.HORIZONTAL_MARGIN,
            0,
            self.HORIZONTAL_MARGIN,
            0,
        )

        layout.setSpacing(0)

        if right:

            layout.addStretch()

            layout.addWidget(
                widget
            )

        else:

            layout.addWidget(
                widget
            )

            layout.addStretch()

        return wrapper

    # =====================================================

    def _add(
        self,
        message: ChatMessage,
    ) -> QWidget:

        bubble = MessageFactory.create(
            message
        )

        wrapper = self._wrap(
            bubble,
            right=(
                message.type
                == MessageType.USER
            ),
        )

        self.messages.addWidget(
            wrapper
        )

        QTimer.singleShot(
            0,
            self.scroll_to_bottom,
        )

        return wrapper

    # =====================================================
    # Public API
    # =====================================================

    def add_user(
        self,
        text: str,
    ) -> None:

        self.hide_thinking()

        self._add(
            ChatMessage(
                MessageType.USER,
                text,
            )
        )

    # -----------------------------------------------------

    def add_mike(
        self,
        text: str,
    ) -> None:

        self.hide_thinking()

        self._add(
            ChatMessage(
                MessageType.MIKE,
                text,
            )
        )

    # -----------------------------------------------------

    def show_planner(
        self,
        text: str,
    ) -> None:

        self._add(
            ChatMessage(
                MessageType.PLANNER,
                text,
            )
        )

    # -----------------------------------------------------

    def show_tool(
        self,
        text: str,
    ) -> None:

        self._add(
            ChatMessage(
                MessageType.TOOL,
                text,
            )
        )

    # -----------------------------------------------------

    def show_system(
        self,
        text: str,
    ) -> None:

        self._add(
            ChatMessage(
                MessageType.SYSTEM,
                text,
            )
        )

    # -----------------------------------------------------

    def show_thinking(
        self,
    ) -> None:

        if self._thinking is not None:

            return

        self._thinking = self._add(
            ChatMessage(
                MessageType.THINKING,
                "",
            )
        )

    # -----------------------------------------------------

    def hide_thinking(
        self,
    ) -> None:

        if self._thinking is None:

            return

        self.messages.removeWidget(
            self._thinking
        )

        self._thinking.deleteLater()

        self._thinking = None

    # -----------------------------------------------------

    def clear(
        self,
    ) -> None:

        self.hide_thinking()

        while self.messages.count():

            item = self.messages.takeAt(
                0
            )

            widget = item.widget()

            if widget is not None:

                widget.deleteLater()

    # -----------------------------------------------------

    def scroll_to_bottom(
        self,
    ) -> None:

        bar = self.scroll.verticalScrollBar()

        QTimer.singleShot(
            0,
            lambda: bar.setValue(
                bar.maximum()
            ),
        )

    # =====================================================

    @property
    def message_count(
        self,
    ) -> int:

        count = self.messages.count()

        if self._thinking is not None:

            count -= 1

        return max(
            0,
            count,
        )