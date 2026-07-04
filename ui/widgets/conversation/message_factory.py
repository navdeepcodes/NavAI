from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ui.widgets.conversation.chat_message import (
    ChatMessage,
    MessageType,
)

from ui.widgets.conversation.mike_bubble import MikeBubble
from ui.widgets.conversation.planner_bubble import PlannerBubble
from ui.widgets.conversation.system_bubble import SystemBubble
from ui.widgets.conversation.thinking_bubble import ThinkingBubble
from ui.widgets.conversation.tool_bubble import ToolBubble
from ui.widgets.conversation.user_bubble import UserBubble


class MessageFactory:
    """
    Factory responsible for converting ChatMessage
    objects into conversation widgets.

    Presentation layer only.
    """

    # =====================================================

    @staticmethod
    def create(
        message: ChatMessage,
    ) -> QWidget:

        if message.type is MessageType.USER:

            return UserBubble(
                message.text
            )

        if message.type is MessageType.MIKE:

            return MikeBubble(
                message.text
            )

        if message.type is MessageType.THINKING:

            return ThinkingBubble()

        if message.type is MessageType.PLANNER:

            return PlannerBubble(
                message.text
            )

        if message.type is MessageType.TOOL:

            return ToolBubble(
                message.text
            )

        if message.type is MessageType.SYSTEM:

            return SystemBubble(
                message.text
            )

        raise RuntimeError(
            f"Unknown message type: {message.type!r}"
        )