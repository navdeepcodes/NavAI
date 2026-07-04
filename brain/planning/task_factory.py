from __future__ import annotations

from logs.logger import logger

from brain.intelligence.thinking_result import ThinkingResult
from brain.planning.task import Task


class TaskFactory:
    """
    Converts a ThinkingResult into executable Tasks.

    Responsibilities
    ----------------
    • Translate cognition into executable tasks.
    • Never perform reasoning.
    • Never execute tools.
    • Never call an LLM.

    The ThinkingEngine decides WHAT to do.
    TaskFactory decides HOW to represent it.
    """

    # =====================================================

    def create_tasks(
        self,
        thinking: ThinkingResult,
    ) -> list[Task]:

        logger.info("Building execution tasks...")

        # -------------------------------------------------
        # No execution required
        # -------------------------------------------------

        if (
            not thinking.requires_tools
            or not thinking.tool
        ):

            return []

        # -------------------------------------------------
        # Build task
        # -------------------------------------------------

        task = Task(

            tool=thinking.tool,

            action=thinking.tool_action or "execute",

            description=thinking.goal or thinking.intent,

            arguments=dict(
                thinking.arguments
            ),

        )

        logger.info(

            "Created task | tool=%s action=%s",

            task.tool,

            task.action,

        )

        return [task]