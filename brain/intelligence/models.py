from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brain.conversation.conversation_models import ConversationState

from brain.intelligence.enums import (
    DecisionAction,
    EmotionLabel,
)


# =========================================================
# Understanding
# =========================================================

@dataclass(slots=True)
class Understanding:
    """
    Mike's semantic understanding of the user's request.

    Determines WHAT the user wants,
    not HOW Mike should respond.
    """

    goal: str = ""

    intent: str = ""

    requires_tools: bool = False

    entities: dict[str, Any] = field(default_factory=dict)

    constraints: dict[str, Any] = field(default_factory=dict)

    confidence: float = 1.0

    emotional_tone: EmotionLabel = EmotionLabel.NEUTRAL


# =========================================================
# Reasoning
# =========================================================

@dataclass(slots=True)
class Reasoning:
    """
    Internal reasoning before decision making.

    Never shown directly to the user.
    """

    thoughts: list[str] = field(default_factory=list)

    observations: list[str] = field(default_factory=list)

    assumptions: list[str] = field(default_factory=list)


# =========================================================
# Decision
# =========================================================

@dataclass(slots=True)
class Decision:
    """
    Mike's executive decision.

    Represents WHAT Mike should do next.
    """

    action: DecisionAction

    confidence: float = 1.0

    reasoning: str = ""

    clarification_question: str | None = None

    requires_planning: bool = False

    requires_memory: bool = False

    requires_clarification: bool = False


# =========================================================
# Context
# =========================================================

@dataclass(slots=True)
class Context:
    """
    Mike's short-term working memory.

    Exists only for the current conversation.
    """

    current_task: str = ""

    previous_messages: list[str] = field(default_factory=list)

    recent_tool_results: list[Any] = field(default_factory=list)

    active_project: str | None = None

    working_directory: str | None = None


# =========================================================
# Emotion
# =========================================================

@dataclass(slots=True)
class Emotion:
    """
    Emotion detected from the user.
    """

    label: EmotionLabel = EmotionLabel.NEUTRAL

    confidence: float = 1.0


# =========================================================
# Confidence
# =========================================================

@dataclass(slots=True)
class Confidence:
    """
    Confidence score describing Mike's understanding.
    """

    score: float = 1.0

    explanation: str = ""


# =========================================================
# Response
# =========================================================

@dataclass(slots=True)
class Response:
    """
    Final natural-language response.
    """

    text: str

    follow_up: str | None = None

    confidence: float = 1.0


# =========================================================
# Reflection
# =========================================================

@dataclass(slots=True)
class Reflection:
    """
    Self-evaluation after execution.

    Used for future learning and recovery.
    """

    success: bool

    retry: bool = False

    reason: str = ""

    alternative_action: str | None = None


# =========================================================
# Mind
# =========================================================

@dataclass(slots=True)
class Mind:
    """
    Complete cognitive snapshot of Mike.

    Every subsystem contributes exactly one part.

    This object is passed throughout Mike's brain.
    """

    # User

    user_message: str

    # Cognitive pipeline

    understanding: Understanding

    reasoning: Reasoning

    conversation: ConversationState

    decision: Decision

    # Session state

    context: Context

    emotion: Emotion

    confidence: Confidence

    # Runtime state

    planner_tasks: list[Any] = field(default_factory=list)

    tool_results: list[Any] = field(default_factory=list)

    # Optional future modules

    memory_result: Any | None = None

    clarification: str | None = None

    reflection: Reflection | None = None