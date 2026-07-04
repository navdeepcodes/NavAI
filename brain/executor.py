from __future__ import annotations

from collections.abc import Iterable

from logs.logger import logger

from brain.task import Task
from core.tool_executor import ToolExecutor
from tools.tool_result import ToolResult


class Executor:
    """
    Mike Execution Engine.

    Responsibilities
    ----------------
    • Execute validated planner tasks.
    • Dispatch tasks to the correct tool.
    • Track execution state.
    • Never perform planning.
    • Never perform reasoning.
    • Never generate responses.

    Future capabilities
    -------------------
    • Parallel execution
    • Dependency graphs
    • Retry policies
    • Cancellation
    • Progress callbacks
    """

    # ---------------------------------------------------------

    def __init__(self) -> None:

        logger.info("Initializing Executor...")

        self._tool_executor = ToolExecutor()

    # ---------------------------------------------------------

    def execute(
        self,
        tasks: Task | Iterable[Task] | None,
    ) -> list[ToolResult]:

        """
        Execute one or more tasks.

        Returns
        -------
        List[ToolResult]
            One ToolResult per executed task.
        """

        if tasks is None:

            logger.warning("Executor received no tasks.")

            return []

        if isinstance(tasks, Task):

            tasks = [tasks]

        results: list[ToolResult] = []

        for task in tasks:

            result = self._execute_task(task)

            if result is not None:

                results.append(result)

        return results

    # ---------------------------------------------------------

    def _execute_task(
        self,
        task: Task,
    ) -> ToolResult | None:

        if not task.executable:

            logger.info(
                "Skipping non-executable task: %s",
                task.description,
            )

            task.mark_complete()

            return None

        logger.info(
            "Executing Tool | tool=%s action=%s",
            task.tool,
            task.action,
        )

        logger.debug(
            "Arguments: %s",
            task.arguments,
        )

        try:

            result = self._tool_executor.execute(

                tool_name=task.tool,

                action=task.action or "",

                **(task.arguments or {}),

            )

            task.mark_complete(result)

            logger.info(
                "Task %s completed successfully.",
                task.id,
            )

            return result

        except Exception as exc:

            logger.exception(
                "Task %s failed.",
                task.id,
            )

            task.mark_failed(exc)

            return ToolResult(

                success=False,

                tool=task.tool or "",

                action=task.action or "",

                error=str(exc),

            )

    # ---------------------------------------------------------

    @property
    def available_tools(
        self,
    ) -> list[str]:

        return self._tool_executor.available_tools()

    # ---------------------------------------------------------

    def reload_tools(
        self,
    ) -> None:

        logger.info("Reloading tool registry...")

        self._tool_executor.reload()