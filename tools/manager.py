from logs.logger import logger

from tools.browser import BrowserTool


class ToolManager:

    def __init__(self):

        logger.info("🛠️ Initializing Tool Manager...")

        self.tools = {}

        self.register(BrowserTool())

        logger.info("🛠️ Tool Manager ready")

    def register(self, tool):

        self.tools[tool.name] = tool

        logger.info(f"Registered tool: {tool.name}")

    def execute(
        self,
        tool_name,
        action,
        **kwargs
    ):

        logger.info(
            f"Executing {tool_name}.{action}"
        )

        tool = self.tools.get(tool_name)

        if tool is None:

            logger.warning(
                f"Unknown tool: {tool_name}"
            )

            return False

        return tool.execute(
            action,
            **kwargs
        )