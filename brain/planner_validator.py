from __future__ import annotations

from logs.logger import logger

from brain.task import Task
from tools.tool_registry import ToolRegistry


class PlannerValidator:
    """
    Validates tasks produced by the planner before execution.

    Validation includes:

    • Tool exists
    • Action exists
    • Required arguments are present
    """

    # ---------------------------------------------------------

    def __init__(self):

        self.registry = ToolRegistry()

    # ---------------------------------------------------------

    def validate(
        self,
        tasks: list[Task]
    ) -> list[Task]:

        validated: list[Task] = []

        for task in tasks:

            if self._validate_task(task):

                validated.append(task)

        logger.info(

            "PlannerValidator: "

            f"{len(validated)}/{len(tasks)} "

            "task(s) validated."

        )

        return validated

    # ---------------------------------------------------------

    def _validate_task(
        self,
        task: Task
    ) -> bool:

        if not task.tool:

            logger.warning(

                f"Task {task.id}: missing tool."

            )

            return False

        tool = self.registry.get(

            task.tool

        )

        if tool is None:

            logger.warning(

                f"Task {task.id}: "

                f"unknown tool '{task.tool}'."

            )

            return False

        if not task.action:

            logger.warning(

                f"Task {task.id}: "

                "missing action."

            )

            return False

        if task.action not in tool.actions:

            logger.warning(

                f"Task {task.id}: "

                f"unsupported action "

                f"'{task.action}' "

                f"for tool "

                f"'{task.tool}'."

            )

            return False

        arguments = task.arguments or {}

        if not tool.validate(

            task.action,

            **arguments

        ):

            logger.warning(

                f"Task {task.id}: "

                "argument validation failed."

            )

            return False

        return True