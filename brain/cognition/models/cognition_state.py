from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brain.cognition.models.goal import Goal


@dataclass(slots=True)
class CognitionState:
    """
    Working memory for a single cognition cycle.

    A new instance is created for every user request.

    This is NOT:
        • long-term memory
        • conversation history
        • knowledge storage

    It represents Mike's temporary cognitive state while
    processing one request.
    """

    # =====================================================
    # Input
    # =====================================================

    user_message: str = ""

    raw_context: str = ""

    # =====================================================
    # Understanding
    # =====================================================

    goal: Goal | None = None

    intent: str = ""

    confidence: float = 0.0

    emotion: str = "neutral"

    # =====================================================
    # Decision
    # =====================================================

    action: str = ""

    requires_tools: bool = False

    tool: str | None = None

    tool_action: str | None = None

    arguments: dict[str, Any] = field(
        default_factory=dict,
    )

    # =====================================================
    # Execution
    # =====================================================

    execution_result: Any | None = None

    execution_error: str | None = None

    # =====================================================
    # Response
    # =====================================================

    final_response: str | None = None

    # =====================================================
    # Metadata
    # =====================================================

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    # =====================================================
    # Helpers
    # =====================================================

    def mark_tool_executed(
        self,
        result: Any,
    ) -> None:

        self.execution_result = result

    # -----------------------------------------------------

    def mark_failed(
        self,
        error: str,
    ) -> None:

        self.execution_error = error

    # -----------------------------------------------------

    def set_goal(
        self,
        goal: Goal,
    ) -> None:

        self.goal = goal

    # -----------------------------------------------------

    @property
    def has_goal(
        self,
    ) -> bool:

        return self.goal is not None

    # -----------------------------------------------------

    @property
    def has_tool(
        self,
    ) -> bool:

        return self.tool is not None

    # -----------------------------------------------------

    @property
    def execution_succeeded(
        self,
    ) -> bool:

        return (
            self.execution_result is not None
            and self.execution_error is None
        )

    # -----------------------------------------------------

    @property
    def execution_failed(
        self,
    ) -> bool:

        return self.execution_error is not Nonew