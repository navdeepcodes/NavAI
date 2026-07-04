from __future__ import annotations

from time import perf_counter

from logs.logger import logger

from brain.execution.execution_report import ExecutionReport
from brain.execution.execution_result import ExecutionResult
from brain.planning.execution_plan import ExecutionPlan
from brain.planning.task import Task

from core.tool_executor import ToolExecutor
from tools.tool_result import ToolResult


class Executor:
    """
    Mike Execution Engine.

    Responsibilities
    ----------------
    • Execute an ExecutionPlan.
    • Dispatch tasks to ToolExecutor.
    • Record execution results.
    • Produce an ExecutionReport.

    This layer never performs reasoning or planning.
    """

    # =====================================================

    def __init__(self) -> None:

        logger.info("Initializing Executor...")

        self._tool_executor = ToolExecutor()

    # =====================================================

    def execute(
        self,
        plan: ExecutionPlan,
    ) -> ExecutionReport:

        logger.info(
            "Executing plan '%s' (%d task%s).",
            plan.id,
            len(plan.tasks),
            "" if len(plan.tasks) == 1 else "s",
        )

        report = ExecutionReport()

        start = perf_counter()

        for task in plan.tasks:

            result = self._execute_task(task)

            report.add(result)

        report.duration_ms = (
            perf_counter() - start
        ) * 1000

        logger.info(
            "Execution finished in %.2f ms.",
            report.duration_ms,
        )

        return report

    # =====================================================

    def _execute_task(
        self,
        task: Task,
    ) -> ExecutionResult:

        if not task.executable:

            logger.info(
                "Skipping task '%s'.",
                task.description,
            )

            task.complete()

            return ExecutionResult(
                success=True,
                message="Task skipped.",
            )

        if not task.tool or not task.action:

            logger.error(
                "Invalid task. tool=%s action=%s",
                task.tool,
                task.action,
            )

            task.fail("Invalid task.")

            return ExecutionResult(
                success=False,
                message="Invalid task.",
                error="Missing tool or action.",
            )

        logger.info(
            "Executing %s.%s",
            task.tool,
            task.action,
        )

        try:

            tool_result: ToolResult = self._tool_executor.execute(
                tool_name=task.tool,
                action=task.action,
                **task.arguments,
            )

            if tool_result.success:

                task.complete(tool_result)

            else:

                task.fail(
                    tool_result.error
                    or tool_result.message
                    or "Tool execution failed."
                )

            return ExecutionResult(
                success=tool_result.success,
                message=tool_result.message,
                data=tool_result,
                error=tool_result.error,
            )

        except Exception as exc:

            logger.exception(
                "Task execution failed."
            )

            task.fail(str(exc))

            return ExecutionResult(
                success=False,
                message="Task execution failed.",
                error=str(exc),
            )

    # =====================================================

    @property
    def available_tools(
        self,
    ) -> list[str]:

        return self._tool_executor.available_tools()

    # =====================================================

    def reload_tools(
        self,
    ) -> None:

        logger.info(
            "Reloading tool registry..."
        )

        self._tool_executor.reload()