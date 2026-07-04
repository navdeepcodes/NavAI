from enum import Enum


class ConversationStyle(str, Enum):

    DIRECT = "direct"

    FRIENDLY = "friendly"

    DETAILED = "detailed"

    EXPLANATORY = "explanatory"

    SOCRATIC = "socratic"

    CASUAL = "casual"

    PROFESSIONAL = "professional"