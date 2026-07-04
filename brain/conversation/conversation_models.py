from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ConversationState:
    """
    Describes HOW Mike should communicate.

    This is not the response.

    It represents conversational behaviour that
    the Response Engine should follow.
    """

    # -----------------------------------------------------
    # Overall behaviour
    # -----------------------------------------------------

    tone: str = "natural"

    communication_style: str = "human"

    relationship_state: str = "neutral"

    response_length: str = "medium"

    # -----------------------------------------------------
    # Emotional expression
    # -----------------------------------------------------

    empathy: float = 0.50

    enthusiasm: float = 0.50

    confidence: float = 0.80

    curiosity: float = 0.50

    humor: float = 0.20

    patience: float = 1.00

    warmth: float = 0.70

    formality: float = 0.40

    # -----------------------------------------------------
    # Conversational behaviour
    # -----------------------------------------------------

    ask_follow_up: bool = False

    acknowledge_user: bool = False

    celebrate: bool = False

    apologize: bool = False

    reassure: bool = False

    challenge_user: bool = False

    # -----------------------------------------------------
    # Future context
    # -----------------------------------------------------

    is_follow_up: bool = False

    continue_previous_topic: bool = False

    referenced_subject: str = ""

    reasoning: str = ""