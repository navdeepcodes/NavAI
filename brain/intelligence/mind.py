from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from brain.conversation.conversation_models import ConversationState

from brain.intelligence.enums import DecisionAction

from brain.intelligence.models import (
    Confidence,
    Context,
    Decision,
    Emotion,
    Reasoning,
    Reflection,
    Understanding,
)


@dataclass(slots=True)
class Mind:
    """
    Mike's complete cognitive state for a single interaction.

    Every cognitive subsystem receives and updates
    the same Mind instance.

        User
          ↓
      Understanding
          ↓
      Conversation
          ↓
       Reasoning
          ↓
        Decision
          ↓
    Memory / Planning
          ↓
    Tool Execution
          ↓
      Response Engine
    """

    # =====================================================
    # Request
    # =====================================================

    user_message: str

    created_at: datetime = field(
        default_factory=datetime.utcnow
    )

    # =====================================================
    # Cognitive State
    # =====================================================

    understanding: Understanding = field(
        default_factory=Understanding
    )

    conversation: ConversationState = field(
        default_factory=ConversationState
    )

    reasoning: Reasoning = field(
        default_factory=Reasoning
    )

    decision: Decision = field(
        default_factory=lambda: Decision(
            action=DecisionAction.RESPOND,
        )
    )

    context: Context = field(
        default_factory=Context
    )

    emotion: Emotion = field(
        default_factory=Emotion
    )

    confidence: Confidence = field(
        default_factory=Confidence
    )

    # =====================================================
    # Memory
    # =====================================================

    memory_result: Any | None = None

    # =====================================================
    # Clarification
    # =====================================================

    clarification: str | None = None

    # =====================================================
    # Planning
    # =====================================================

    planner_tasks: list[Any] = field(
        default_factory=list
    )

    # =====================================================
    # Tool Execution
    # =====================================================

    tool_results: list[Any] = field(
        default_factory=list
    )

    execution_time_ms: float = 0.0

    # =====================================================
    # Reflection
    # =====================================================

    reflection: Reflection | None = None

    # =====================================================
    # Final Response
    # =====================================================

    final_response: str | None = None

    # =====================================================
    # Metadata
    # =====================================================

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================
    # Helper Methods
    # =====================================================

    def add_task(self, task: Any) -> None:
        self.planner_tasks.append(task)

    def add_tool_result(self, result: Any) -> None:
        self.tool_results.append(result)

    def clear_execution(self) -> None:
        self.planner_tasks.clear()
        self.tool_results.clear()
        self.execution_time_ms = 0.0
        self.reflection = None

    # =====================================================
    # Convenience Properties
    # =====================================================

    @property
    def latest_tool_result(self) -> Any | None:
        return self.tool_results[-1] if self.tool_results else None

    @property
    def requires_tools(self) -> bool:
        return self.decision.requires_planning

    @property
    def is_conversation(self) -> bool:
        return self.decision.action is DecisionAction.RESPOND

    @property
    def has_memory(self) -> bool:
        return self.memory_result is not None

    @property
    def has_tool_results(self) -> bool:
        return bool(self.tool_results)

    @property
    def has_clarification(self) -> bool:
        return self.clarification is not None