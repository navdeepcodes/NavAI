from __future__ import annotations

from brain.intelligence.models import (
    Context,
    Reasoning,
    Understanding,
)


class ReasoningEngine:
    """
    Generates Mike's internal reasoning.

    This reasoning is NEVER shown directly to the user.
    It helps Mike decide the best strategy before acting.
    """

    # ---------------------------------------------------------

    def reason(
        self,
        understanding: Understanding,
        context: Context,
    ) -> Reasoning:

        reasoning = Reasoning()

        # -------------------------------------------------
        # Goal
        # -------------------------------------------------

        reasoning.thoughts.append(

            f"The user's goal is '{understanding.goal}'."

        )

        # -------------------------------------------------
        # Tool Usage
        # -------------------------------------------------

        if understanding.requires_tools:

            reasoning.thoughts.append(

                "This request requires tool execution."

            )

        else:

            reasoning.thoughts.append(

                "This can likely be answered conversationally."

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

            reasoning.assumptions.append(

                "Understanding confidence is low."

            )

            reasoning.assumptions.append(

                "A clarification may be needed."

            )

        else:

            reasoning.assumptions.append(

                "Understanding confidence is sufficient."

            )

        return reasoning