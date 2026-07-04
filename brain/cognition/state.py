from enum import Enum


class CognitiveState(str, Enum):
    """
    Mike's current cognitive state.
    """

    IDLE = "idle"

    LISTENING = "listening"

    UNDERSTANDING = "understanding"

    THINKING = "thinking"

    REASONING = "reasoning"

    DECIDING = "deciding"

    PLANNING = "planning"

    EXECUTING = "executing"

    OBSERVING = "observing"

    REFLECTING = "reflecting"

    RESPONDING = "responding"

    LEARNING = "learning"

    ERROR = "error"