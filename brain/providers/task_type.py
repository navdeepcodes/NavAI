from enum import Enum


class TaskType(str, Enum):

    CHAT = "chat"

    CODING = "coding"

    REASONING = "reasoning"

    VISION = "vision"

    TOOL = "tool"

    MEMORY = "memory"

    PLANNING = "planning"