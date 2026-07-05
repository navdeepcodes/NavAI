from __future__ import annotations

from logs.logger import logger

from brain.cognition.models.cognition_state import CognitionState
from brain.planning.task import Task


class TaskFactory:
    """
    Converts a CognitionState into executable Tasks.

    Responsibilities
    ----------------
    • Translate cognition into executable tasks.
    • Never perform reasoning.
    • Never execute tools.
    • Never call an LLM.

    Understanding decides WHAT the user means.
    Decision decides WHAT Mike should do.
    TaskFactory converts that into executable tasks.
    """

    # =====================================================

    def create_tasks(
        self,
        state: CognitionState,
    ) -> list[Task]:

        logger.info("Building execution tasks...")

        # -------------------------------------------------
        # Nothing to execute
        # -------------------------------------------------

        if not state.requires_tools:

            logger.info(
                "No execution required."
            )

            return []

        # -------------------------------------------------
        # Validate execution information
        # -------------------------------------------------

        if not state.tool:

            logger.warning(
                "Execution requested but no tool specified."
            )

            return []

        # -------------------------------------------------
        # Build task
        # -------------------------------------------------

        task = Task(

            tool=state.tool,

            action=state.tool_action or "execute",

            description=state.goal or state.intent,

            arguments=dict(state.arguments),

        )

        logger.info(

            "Created task | tool=%s | action=%s",

            task.tool,

            task.action,

        )

        return [task]