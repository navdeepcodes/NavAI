from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):

    SYSTEM = "system"

    USER = "user"

    ASSISTANT = "assistant"

    TOOL = "tool"


@dataclass(slots=True)
class Message:

    role: Role

    content: str