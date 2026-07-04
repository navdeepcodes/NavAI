from __future__ import annotations

from dataclasses import dataclass, field

from brain.intelligence.enums import (
    ConversationStyle,
    EmotionLabel,
)


# =========================================================
# Emotion Analysis
# =========================================================

@dataclass(slots=True)
class EmotionAnalysis:
    """
    Emotional state detected from the user's message.
    """

    label: EmotionLabel = EmotionLabel.NEUTRAL

    confidence: float = 1.0

    intensity: float = 0.5

    explanation: str = ""

    response_hint: str = ""


# =========================================================
# Cognitive Analysis
# =========================================================

@dataclass(slots=True)
class CognitiveAnalysis:
    """
    Complete semantic understanding of the user's request.

    Produced by the Analyzer.

    Every downstream intelligence module consumes this object.
    """

    # -----------------------------------------------------
    # Intent
    # -----------------------------------------------------

    intent: str

    goal: str

    # -----------------------------------------------------
    # Tool Routing
    # -----------------------------------------------------

    requires_tools: bool = False

    # -----------------------------------------------------
    # Context
    # -----------------------------------------------------

    entities: dict = field(default_factory=dict)

    constraints: dict = field(default_factory=dict)

    # -----------------------------------------------------
    # Conversation
    # -----------------------------------------------------

    emotion: EmotionAnalysis = field(

        default_factory=EmotionAnalysis

    )

    conversation_style: ConversationStyle = (

        ConversationStyle.FRIENDLY

    )

    urgency: str = "normal"

    # -----------------------------------------------------
    # Confidence
    # -----------------------------------------------------

    confidence: float = 1.0