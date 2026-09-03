from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
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

from ui.widgets.conversation.welcome_panel import (
    WelcomePanel,
)


class ConversationPanel(QWidget):

    suggestion_clicked = Signal(str)

    CONTENT_PADDING = 40

    def __init__(self) -> None:

        super().__init__()

        self._thinking: QWidget | None = None
        self._user_scrolled_up = False

        self._build_ui()

    def _build_ui(self) -> None:

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()

        # Page 0: Welcome

        self._welcome = WelcomePanel()
        self._welcome.suggestion_clicked.connect(
            self.suggestion_clicked.emit
        )
        self._stack.addWidget(self._welcome)

        # Page 1: Conversation

        conv_page = QWidget()
        conv_layout = QVBoxLayout(conv_page)
        conv_layout.setContentsMargins(0, 0, 0, 0)
        conv_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        vbar = self.scroll.verticalScrollBar()
        vbar.valueChanged.connect(self._on_scroll)

        self.container = QWidget()

        self.messages = QVBoxLayout(self.container)
        self.messages.setContentsMargins(
            self.CONTENT_PADDING, 24,
            self.CONTENT_PADDING, 24,
        )
        self.messages.setSpacing(12)
        self.messages.setAlignment(Qt.AlignTop)

        self.scroll.setWidget(self.container)
        conv_layout.addWidget(self.scroll)

        self._stack.addWidget(conv_page)
        self._stack.setCurrentIndex(0)

        root.addWidget(self._stack)

    def _on_scroll(self) -> None:

        bar = self.scroll.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 40
        self._user_scrolled_up = not at_bottom

    def _ensure_conversation(self) -> None:

        if self._stack.currentIndex() == 0:
            self._stack.setCurrentIndex(1)

    def _wrap(
        self,
        widget: QWidget,
        *,
        right: bool = False,
    ) -> QWidget:

        wrapper = QWidget()

        wrapper.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )

        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if right:
            layout.addStretch(1)
            layout.addWidget(widget, 0)
        else:
            layout.addWidget(widget, 1)
            layout.addStretch(0)

        return wrapper

    def _add(self, message: ChatMessage) -> QWidget:

        self._ensure_conversation()

        bubble = MessageFactory.create(message)

        wrapper = self._wrap(
            bubble,
            right=(message.type == MessageType.USER),
        )

        self.messages.addWidget(wrapper)

        self._smart_scroll()

        return wrapper

    def _smart_scroll(self) -> None:

        if not self._user_scrolled_up:
            QTimer.singleShot(0, self.scroll_to_bottom)

    # Public API

    def add_user(self, text: str) -> None:

        self.hide_thinking()
        self._add(ChatMessage(MessageType.USER, text))

    def add_mike(self, text: str) -> None:

        self.hide_thinking()
        self._add(ChatMessage(MessageType.MIKE, text))

    def begin_mike_stream(self):

        self._ensure_conversation()
        self.hide_thinking()

        bubble = MessageFactory.create(
            ChatMessage(MessageType.MIKE, "")
        )

        wrapper = self._wrap(bubble)
        self.messages.addWidget(wrapper)
        self._smart_scroll()

        return bubble

    def add_action_card(self, text: str):

        self._ensure_conversation()
        self.hide_thinking()

        from ui.widgets.conversation.tool_bubble import ToolBubble

        card = ToolBubble(text)
        wrapper = self._wrap(card)
        self.messages.addWidget(wrapper)
        self._smart_scroll()

        return card

    def show_planner(self, text: str) -> None:

        self._add(ChatMessage(MessageType.PLANNER, text))

    def show_tool(self, text: str) -> None:

        self._add(ChatMessage(MessageType.TOOL, text))

    def show_system(self, text: str) -> None:

        self._add(ChatMessage(MessageType.SYSTEM, text))

    def show_thinking(self) -> None:

        self._ensure_conversation()

        if self._thinking is not None:
            return

        self._thinking = self._add(
            ChatMessage(MessageType.THINKING, "")
        )

    def hide_thinking(self) -> None:

        if self._thinking is None:
            return

        self.messages.removeWidget(self._thinking)
        self._thinking.deleteLater()
        self._thinking = None

    def clear(self) -> None:

        self.hide_thinking()

        while self.messages.count():
            item = self.messages.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._stack.setCurrentIndex(0)

    def scroll_to_bottom(self) -> None:

        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(
            0,
            lambda: bar.setValue(bar.maximum()),
        )

    @property
    def message_count(self) -> int:

        count = self.messages.count()

        if self._thinking is not None:
            count -= 1

        return max(0, count)
