from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ThinkingResult:
    """
    Canonical output of Mike's Thinking Engine.

    ThinkingResult is the single contract shared by
    Runtime, Planner, Executor, Memory and Response.

    The ThinkingEngine decides WHAT should happen.
    Every downstream subsystem simply executes it.
    """

    # =====================================================
    # Understanding
    # =====================================================

    intent: str
    goal: str
    confidence: float
    emotion: str
    tone: str

    # =====================================================
    # Executive Decision
    # =====================================================

    action: str
    requires_tools: bool

    # =====================================================
    # Tool Execution
    # =====================================================

    tool: str | None = None
    tool_action: str | None = None

    arguments: dict[str, Any] = field(
        default_factory=dict
    )

    execution_type: str = "single"

    # =====================================================
    # Response
    # =====================================================

    response: str = ""

    # =====================================================
    # Optional Outputs
    # =====================================================

    clarification: str | None = None
    planner_hint: str | None = None
    memory_query: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================

    def __post_init__(self) -> None:

        self.intent = str(self.intent).strip()

        self.goal = str(self.goal).strip()

        self.emotion = str(self.emotion).strip().lower()

        self.tone = str(self.tone).strip().lower()

        self.action = str(self.action).strip().upper()

        self.response = str(self.response).strip()

        self.clarification = (
            self.clarification.strip()
            if isinstance(self.clarification, str)
            else None
        )

        self.planner_hint = (
            self.planner_hint.strip()
            if isinstance(self.planner_hint, str)
            else None
        )

        self.memory_query = (
            self.memory_query.strip()
            if isinstance(self.memory_query, str)
            else None
        )

        self.tool = (
            self.tool.strip().lower()
            if isinstance(self.tool, str)
            else None
        )

        self.tool_action = (
            self.tool_action.strip().lower()
            if isinstance(self.tool_action, str)
            else None
        )

        self.execution_type = (
            str(self.execution_type).strip().lower()
            if self.execution_type
            else "single"
        )

        self.arguments = dict(self.arguments or {})

        self.metadata = dict(self.metadata or {})

        self.confidence = max(
            0.0,
            min(
                float(self.confidence),
                1.0,
            ),
        )

        self._normalize()

    # =====================================================

    def _normalize(self) -> None:
        """
        Eliminate impossible cognitive states.
        """

        # -----------------------------------------
        # RESPOND
        # -----------------------------------------

        if self.action == "RESPOND":

            self.requires_tools = False
            self.tool = None
            self.tool_action = None
            self.arguments = {}
            self.execution_type = "single"

            return

        # -----------------------------------------
        # PLAN
        # -----------------------------------------

        if self.action == "PLAN":

            if not self.tool or not self.tool_action:
                self.action = "RESPOND"
                self.requires_tools = False
                self.tool = None
                self.tool_action = None
                self.arguments = {}

            else:
                self.requires_tools = True

            return

        # -----------------------------------------
        # MEMORY
        # -----------------------------------------

        if self.action == "MEMORY":

            self.requires_tools = False
            self.tool = None
            self.tool_action = None
            self.arguments = {}

            return

        # -----------------------------------------
        # CLARIFY
        # -----------------------------------------

        if self.action == "CLARIFY":

            self.requires_tools = False
            self.tool = None
            self.tool_action = None
            self.arguments = {}

            if not self.clarification:
                self.clarification = (
                    "Could you clarify your request?"
                )

            return

        # -----------------------------------------
        # IGNORE
        # -----------------------------------------

        if self.action == "IGNORE":

            self.requires_tools = False
            self.tool = None
            self.tool_action = None
            self.arguments = {}

    # =====================================================
    # Helpers
    # =====================================================

    @property
    def should_respond(self) -> bool:
        return self.action == "RESPOND"

    @property
    def should_plan(self) -> bool:
        return self.action == "PLAN"

    @property
    def should_clarify(self) -> bool:
        return self.action == "CLARIFY"

    @property
    def should_use_memory(self) -> bool:
        return self.action == "MEMORY"

    @property
    def should_ignore(self) -> bool:
        return self.action == "IGNORE"

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.70

    @property
    def has_response(self) -> bool:
        return bool(self.response)

    @property
    def has_tool(self) -> bool:
        return self.tool is not None

    @property
    def has_tool_action(self) -> bool:
        return self.tool_action is not None

    @property
    def has_arguments(self) -> bool:
        return bool(self.arguments)

    @property
    def executable(self) -> bool:
        return (
            self.action == "PLAN"
            and self.requires_tools
            and self.tool is not None
            and self.tool_action is not None
        )