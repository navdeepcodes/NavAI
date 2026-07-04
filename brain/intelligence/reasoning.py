from __future__ import annotations

from brain.intelligence.models import (
    Context,
    Reasoning,
    Understanding,
)


class ReasoningEngine:
    """
    Builds Mike's internal reasoning.

    This module performs deterministic reasoning only.
    It never calls an LLM and never generates user-facing text.

    Responsibilities
    ----------------
    • Explain Mike's internal reasoning
    • Summarize available context
    • Record assumptions
    • Assess confidence
    """

    # =====================================================

    def reason(
        self,
        understanding: Understanding,
        context: Context,
    ) -> Reasoning:

        reasoning = Reasoning()

        # -------------------------------------------------
        # User Goal
        # -------------------------------------------------

        if understanding.goal:

            reasoning.thoughts.append(
                f"Primary goal: {understanding.goal}"
            )

        # -------------------------------------------------
        # Tool Requirement
        # -------------------------------------------------

        reasoning.thoughts.append(
            "Tool execution required."
            if understanding.requires_tools
            else "Conversational response is sufficient."
        )

        # -------------------------------------------------
        # Context
        # -------------------------------------------------

        if context.current_task:
            reasoning.observations.append(
                f"Current task: {context.current_task}"
            )

        if context.active_project:
            reasoning.observations.append(
                f"Active project: {context.active_project}"
            )

        if context.working_directory:
            reasoning.observations.append(
                f"Working directory: {context.working_directory}"
            )

        # -------------------------------------------------
        # Confidence
        # -------------------------------------------------

        if understanding.confidence < 0.70:

            reasoning.assumptions.extend(
                [
                    "Understanding confidence is low.",
                    "Clarification may be required.",
                ]
            )

        else:

            reasoning.assumptions.append(
                "Understanding confidence is sufficient."
            )

        return reasoning