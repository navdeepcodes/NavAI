from enum import Enum


# ---------------------------------------------------------
# Decision Actions
# ---------------------------------------------------------

class DecisionAction(str, Enum):
    """
    The next action Mike should take after reasoning.
    """

    RESPOND = "respond"

    PLAN = "plan"

    CLARIFY = "clarify"

    REFUSE = "refuse"

    MEMORY = "memory"


# ---------------------------------------------------------
# Emotion Labels
# ---------------------------------------------------------

class EmotionLabel(str, Enum):

    HAPPY = "happy"

    EXCITED = "excited"

    NEUTRAL = "neutral"

    CURIOUS = "curious"

    CONFUSED = "confused"

    FRUSTRATED = "frustrated"

    SAD = "sad"

    URGENT = "urgent"


# ---------------------------------------------------------
# Conversation Style
# ---------------------------------------------------------

class ConversationStyle(str, Enum):

    DIRECT = "direct"

    FRIENDLY = "friendly"

    CASUAL = "casual"

    PROFESSIONAL = "professional"

    DETAILED = "detailed"

    EXPLANATORY = "explanatory"

    SOCRATIC = "socratic"