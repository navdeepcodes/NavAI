from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class MessageType(Enum):
    """
    Conversation message types.
    """

    USER = auto()

    MIKE = auto()

    THINKING = auto()

    PLANNER = auto()

    TOOL = auto()

    SYSTEM = auto()


@dataclass(slots=True)
class ChatMessage:
    """
    Immutable conversation message.
    """

    type: MessageType

    text: str

    metadata: dict[str, object] | None = None