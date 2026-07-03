from logs.logger import logger

from tools.tool_registry import ToolRegistry


class ToolExecutor:

    def __init__(self):

        self.registry = ToolRegistry()

    # -----------------------------------------

    def execute(
        self,
        tool_name: str,
        **kwargs
    ):

        logger.info(

            f"Executing tool: {tool_name}"

        )

        return self.registry.execute(

            tool_name,

            **kwargs

        )

    # -----------------------------------------

    def available_tools(self):

        return self.registry.available()

    # -----------------------------------------

    def has_tool(
        self,
        tool_name: str
    ):

        return self.registry.has(
            tool_name
        )