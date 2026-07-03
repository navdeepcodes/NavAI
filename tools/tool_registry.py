import inspect
import importlib
import pkgutil

from logs.logger import logger

import tools

from tools.base_tool import BaseTool


class ToolRegistry:

    def __init__(self):

        self.tools = {}

        self._discover_tools()

    # -----------------------------------------

    def _discover_tools(self):

        logger.info(
            "Discovering tools..."
        )

        for _, module_name, _ in pkgutil.iter_modules(
            tools.__path__
        ):

            if module_name in [

                "__init__",

                "base_tool",

                "tool_registry"

            ]:

                continue

            module = importlib.import_module(

                f"tools.{module_name}"

            )

            for _, obj in inspect.getmembers(

                module,

                inspect.isclass

            ):

                if (

                    issubclass(

                        obj,

                        BaseTool

                    )

                    and obj is not BaseTool

                ):

                    tool = obj()

                    self.register(

                        tool

                    )

    # -----------------------------------------

    def register(
        self,
        tool
    ):

        logger.info(

            f"Registering tool: {tool.name}"

        )

        self.tools[
            tool.name
        ] = tool

    # -----------------------------------------

    def has(
        self,
        name: str
    ):

        return name in self.tools

    # -----------------------------------------

    def get(
        self,
        name: str
    ):

        return self.tools.get(
            name
        )

    # -----------------------------------------

    def execute(
        self,
        name: str,
        **kwargs
    ):

        tool = self.get(
            name
        )

        if tool is None:

            raise ValueError(

                f"Unknown tool: {name}"

            )

        return tool.execute(
            **kwargs
        )

    # -----------------------------------------

    def available(self):

        return sorted(

            self.tools.keys()

        )