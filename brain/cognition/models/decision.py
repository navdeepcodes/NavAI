from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Decision:
    """
    Represents Mike's decision after understanding the user's intent.

    Understanding answers:
        "What does the user mean?"

    Decision answers:
        "What should Mike do?"

    This model contains no execution logic.
    """

    # =====================================================
    # Core Decision
    # =====================================================

    action: str

    confidence: float

    reasoning: str = ""

    # =====================================================
    # Decision Flags
    # =====================================================

    requires_response: bool = True

    requires_execution: bool = False

    requires_memory: bool = False

    requires_clarification: bool = False

    # =====================================================
    # Execution
    # =====================================================

    execution_goal: str | None = None

    tool: str | None = None

    tool_action: str | None = None

    arguments: dict[str, Any] = field(
        default_factory=dict
    )

    planner_hint: str | None = None

    # =====================================================
    # Memory
    # =====================================================

    memory_operation: str | None = None

    # =====================================================
    # Metadata
    # =====================================================

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================
    # Convenience
    # =====================================================

    @property
    def should_execute(self) -> bool:
        return self.requires_execution

    @property
    def should_respond(self) -> bool:
        return self.requires_response

    @property
    def should_use_memory(self) -> bool:
        return self.requires_memory

    @property
    def should_clarify(self) -> bool:
        return self.requires_clarification

    @property
    def has_tool(self) -> bool:
        return self.tool is not None

    @property
    def has_arguments(self) -> bool:
        return bool(self.arguments)