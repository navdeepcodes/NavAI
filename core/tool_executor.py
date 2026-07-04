from __future__ import annotations

from time import perf_counter

from logs.logger import logger

from tools.tool_context import ToolContext
from tools.tool_result import ToolResult
from tools.tool_registry import ToolRegistry


class ToolExecutor:

    # ---------------------------------------------------------

    def __init__(self) -> None:

        self.registry = ToolRegistry()

    # ---------------------------------------------------------

    def execute(
        self,
        tool_name: str,
        context: ToolContext | None = None,
        **kwargs,
    ) -> ToolResult:

        logger.info(
            "Executing Tool: %s",
            tool_name,
        )

        tool = self.registry.get(tool_name)

        if tool is None:
            raise ValueError(
                f"Unknown tool: {tool_name}"
            )

        if context is None:
            context = ToolContext()

        action = str(
            kwargs.get("action", "")
        )

        # -------------------------------------------------

        if not tool.validate(**kwargs):

            return ToolResult(
                success=False,
                tool=tool.metadata.name,
                action=action,
                message="",
                error="Validation failed.",
            )

        # -------------------------------------------------

        start = perf_counter()

        try:

            result = tool.execute(
                context=context,
                **kwargs,
            )

            result.execution_time_ms = (
                perf_counter() - start
            ) * 1000

            logger.info(
                "%s completed in %.2f ms",
                tool.metadata.name,
                result.execution_time_ms,
            )

            return result

        except Exception as e:

            logger.exception(e)

            return ToolResult(
                success=False,
                tool=tool.metadata.name,
                action=action,
                message="",
                error=str(e),
            )

        finally:

            tool.cleanup()

    # ---------------------------------------------------------

    def available_tools(self):

        return self.registry.available()

    # ---------------------------------------------------------

    def has_tool(
        self,
        tool_name: str,
    ):

        return self.registry.has(tool_name)

    # ---------------------------------------------------------

    def reload(self):

        self.registry.reload()