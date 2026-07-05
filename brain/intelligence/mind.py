from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from brain.intelligence.thinking_result import ThinkingResult


@dataclass(slots=True)
class Mind:
    """
    Mike's cognitive state for a single interaction.

    Every request produces exactly one ThinkingResult.

    Planner, Executor, Conversation and Memory extend this
    object without performing additional reasoning.
    """

    # =====================================================
    # Request
    # =====================================================

    user_message: str

    thinking: ThinkingResult

    created_at: datetime = field(
        default_factory=datetime.utcnow
    )

    # =====================================================
    # Conversation
    # =====================================================

    conversation_memory: Any | None = None

    # =====================================================
    # Memory
    # =====================================================

    memory_result: Any | None = None

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

    def add_task(
        self,
        task: Any,
    ) -> None:

        self.planner_tasks.append(task)

    # -----------------------------------------------------

    def add_tool_result(
        self,
        result: Any,
    ) -> None:

        self.tool_results.append(result)

    # -----------------------------------------------------

    def clear_execution(
        self,
    ) -> None:

        self.planner_tasks.clear()
        self.tool_results.clear()
        self.execution_time_ms = 0.0

    # =====================================================
    # Convenience Properties
    # =====================================================

    @property
    def latest_tool_result(
        self,
    ) -> Any | None:

        if not self.tool_results:
            return None

        return self.tool_results[-1]

    # -----------------------------------------------------

    @property
    def has_tool_results(
        self,
    ) -> bool:

        return bool(self.tool_results)

    # -----------------------------------------------------

    @property
    def has_memory(
        self,
    ) -> bool:

        return self.memory_result is not None

    # -----------------------------------------------------

    @property
    def has_conversation(
        self,
    ) -> bool:

        return self.conversation_memory is not None

    # =====================================================
    # Thinking Shortcuts
    # =====================================================

    @property
    def action(
        self,
    ) -> str:

        return self.thinking.action

    # -----------------------------------------------------

    @property
    def intent(
        self,
    ) -> str:

        return self.thinking.intent

    # -----------------------------------------------------

    @property
    def goal(
        self,
    ) -> str:

        return self.thinking.goal

    # -----------------------------------------------------

    @property
    def confidence(
        self,
    ) -> float:

        return self.thinking.confidence

    # -----------------------------------------------------

    @property
    def emotion(
        self,
    ) -> str:

        return self.thinking.emotion

    # -----------------------------------------------------

    @property
    def tone(
        self,
    ) -> str:

        return self.thinking.tone

    # -----------------------------------------------------

    @property
    def requires_tools(
        self,
    ) -> bool:

        return self.thinking.requires_tools

    # -----------------------------------------------------

    @property
    def tool(
        self,
    ) -> str | None:

        return self.thinking.tool

    # -----------------------------------------------------

    @property
    def response(
        self,
    ) -> str:
        """
        Final response precedence

        1. Runtime-generated response
        2. ThinkingEngine response
        """

        if self.final_response:
            return self.final_response.strip()

        if self.thinking.response:
            return self.thinking.response.strip()

        return ""

    # -----------------------------------------------------

    @property
    def should_respond(
        self,
    ) -> bool:

        return self.thinking.should_respond

    # -----------------------------------------------------

    @property
    def should_plan(
        self,
    ) -> bool:

        return self.thinking.should_plan

    # -----------------------------------------------------

    @property
    def should_clarify(
        self,
    ) -> bool:

        return self.thinking.should_clarify

    # -----------------------------------------------------

    @property
    def should_use_memory(
        self,
    ) -> bool:

        return self.thinking.should_use_memory