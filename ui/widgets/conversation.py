from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
)


# ==========================================================
# Message Bubble
# ==========================================================


class MessageBubble(QWidget):

    def __init__(
        self,
        text: str,
        *,
        user: bool,
    ) -> None:

        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)

        bubble = QLabel(text)

        bubble.setWordWrap(True)

        bubble.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        bubble.setMaximumWidth(700)

        bubble.setStyleSheet(
            f"""
            QLabel {{
                padding:14px;
                border-radius:14px;

                background:
                    {"#0f172a" if user else "#111111"};

                border:1px solid #222;

                color:white;

                font-size:14px;
            }}
            """
        )

        if user:

            layout.addStretch()

            layout.addWidget(bubble)

        else:

            layout.addWidget(bubble)

            layout.addStretch()


# ==========================================================
# Thinking Bubble
# ==========================================================


class ThinkingBubble(QWidget):

    def __init__(self) -> None:

        super().__init__()

        layout = QHBoxLayout(self)

        layout.setContentsMargins(12, 6, 12, 6)

        self.label = QLabel(
            "Mike is thinking..."
        )

        self.label.setStyleSheet(
            """
            QLabel{

                color:#888;

                padding:12px;

                font-size:13px;
            }
            """
        )

        layout.addWidget(self.label)

        layout.addStretch()

        self._dots = 0

    def tick(self) -> None:

        self._dots += 1

        if self._dots > 3:

            self._dots = 0

        self.label.setText(

            "Mike is thinking"

            + "." * self._dots

        )


# ==========================================================
# Conversation Panel
# ==========================================================


class ConversationPanel(QWidget):

    def __init__(self) -> None:

        super().__init__()

        root = QVBoxLayout(self)

        root.setContentsMargins(0, 0, 0, 0)

        root.setSpacing(0)

        self.scroll = QScrollArea()

        self.scroll.setWidgetResizable(True)

        self.scroll.setFrameShape(
            QScrollArea.NoFrame
        )

        self.container = QWidget()

        self.messages = QVBoxLayout(
            self.container
        )

        self.messages.setAlignment(
            Qt.AlignTop
        )

        self.messages.setSpacing(8)

        self.scroll.setWidget(
            self.container
        )

        root.addWidget(self.scroll)

        self.thinking = None

    # -----------------------------------------------------

    def add_user(
        self,
        text: str,
    ) -> None:

        self.messages.addWidget(

            MessageBubble(

                text,

                user=True,

            )

        )

        self.scroll_to_bottom()

    # -----------------------------------------------------

    def add_mike(
        self,
        text: str,
    ) -> None:

        if self.thinking:

            self.messages.removeWidget(
                self.thinking
            )

            self.thinking.deleteLater()

            self.thinking = None

        self.messages.addWidget(

            MessageBubble(

                text,

                user=False,

            )

        )

        self.scroll_to_bottom()

    # -----------------------------------------------------

    def show_thinking(self) -> None:

        if self.thinking:

            return

        self.thinking = ThinkingBubble()

        self.messages.addWidget(
            self.thinking
        )

        self.scroll_to_bottom()

    # -----------------------------------------------------

    def hide_thinking(self) -> None:

        if not self.thinking:

            return

        self.messages.removeWidget(
            self.thinking
        )

        self.thinking.deleteLater()

        self.thinking = None

    # -----------------------------------------------------

    def scroll_to_bottom(self):

        bar = self.scroll.verticalScrollBar()

        bar.setValue(
            bar.maximum()
        )