from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class MessageRole(Enum):
    """
    The origin/type of a conversation message.
    """

    USER = auto()

    ASSISTANT = auto()

    SYSTEM = auto()

    TOOL = auto()

    THINKING = auto()

    PLANNER = auto()

    ERROR = auto()


@dataclass(slots=True)
class ChatMessage:
    """
    Immutable message model used by the conversation UI.

    Every item rendered inside the conversation panel is first
    represented as a ChatMessage.

    Examples
    --------
    User message

        ChatMessage(
            role=MessageRole.USER,
            text="Open Chrome"
        )

    Assistant message

        ChatMessage(
            role=MessageRole.ASSISTANT,
            text="Opening Chrome..."
        )

    Tool result

        ChatMessage(
            role=MessageRole.TOOL,
            title="Browser",
            text="Chrome opened successfully."
        )
    """

    role: MessageRole

    text: str

    title: str = ""

    timestamp: datetime = field(
        default_factory=datetime.now
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    streaming: bool = False

    completed: bool = True

    selectable: bool = True

    copyable: bool = True

    # -----------------------------------------------------

    @property
    def is_user(self) -> bool:

        return self.role == MessageRole.USER

    @property
    def is_assistant(self) -> bool:

        return self.role == MessageRole.ASSISTANT

    @property
    def is_system(self) -> bool:

        return self.role == MessageRole.SYSTEM

    @property
    def is_tool(self) -> bool:

        return self.role == MessageRole.TOOL

    @property
    def is_planner(self) -> bool:

        return self.role == MessageRole.PLANNER

    @property
    def is_thinking(self) -> bool:

        return self.role == MessageRole.THINKING

    @property
    def is_error(self) -> bool:

        return self.role == MessageRole.ERROR

    # -----------------------------------------------------

    def append(self, token: str) -> None:
        """
        Append streamed text.
        """

        self.text += token

    # -----------------------------------------------------

    def finish(self) -> None:
        """
        Mark streaming complete.
        """

        self.streaming = False
        self.completed = True