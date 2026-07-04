from __future__ import annotations

from logs.logger import logger

from brain.intelligence.thinking_result import ThinkingResult
from brain.planning.execution_plan import ExecutionPlan
from brain.planning.task_factory import TaskFactory


class Planner:
    """
    Mike's execution planner.

    Converts a ThinkingResult into an ExecutionPlan.

    Responsibilities
    ----------------
    • Build an execution plan.
    • Delegate task creation.
    • Never perform reasoning.
    • Never execute tasks.
    """

    # =====================================================

    def __init__(self) -> None:

        self._factory = TaskFactory()

    # =====================================================

    def plan(
        self,
        thinking: ThinkingResult,
    ) -> ExecutionPlan:

        logger.info("Planning execution...")

        plan = ExecutionPlan(
            goal=thinking.goal or thinking.intent,
        )

        # -------------------------------------------------
        # Nothing to execute
        # -------------------------------------------------

        if not thinking.requires_tools:

            logger.info(
                "Thinking result does not require tool execution."
            )

            return plan

        # -------------------------------------------------
        # Build tasks
        # -------------------------------------------------

        tasks = self._factory.create_tasks(
            thinking,
        )

        if not tasks:

            logger.warning(
                "TaskFactory returned no executable tasks."
            )

            return plan

        # -------------------------------------------------
        # Populate plan
        # -------------------------------------------------

        for task in tasks:

            plan.add_task(task)

        logger.info(
            "Execution plan created (%d task%s).",
            len(plan.tasks),
            "" if len(plan.tasks) == 1 else "s",
        )

        return plan