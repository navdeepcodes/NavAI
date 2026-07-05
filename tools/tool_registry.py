from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType

import tools

from brain.self.capability_registry import CapabilityRegistry
from logs.logger import logger
from tools.base_tool import BaseTool


class ToolRegistry:
    """
    Automatically discovers and registers all tools.

    Discovery is recursive.

    Every concrete subclass of BaseTool is instantiated once.

    Duplicate module imports and duplicate tool registrations are ignored.

    Every discovered tool is also registered as one of Mike's capabilities.
    """

    # ---------------------------------------------------------

    SKIP_MODULES = {
        "__init__",
        "__pycache__",
        "base_tool",
        "tool_registry",
        "tool_metadata",
        "tool_result",
        "tool_context",
        "tool_permission",
        "schema",
    }

    # ---------------------------------------------------------

    def __init__(self) -> None:

        self.tools: dict[str, BaseTool] = {}

        #
        # Mike's self-awareness starts here.
        #
        self.capabilities = CapabilityRegistry()

        self._visited_modules: set[str] = set()

        self._registered_classes: set[type] = set()

        self._discover_package(tools)

    # ---------------------------------------------------------

    def _discover_package(
        self,
        package: ModuleType,
    ) -> None:

        logger.info(
            "Discovering package: %s",
            package.__name__,
        )

        for module_info in pkgutil.iter_modules(package.__path__):

            name = module_info.name

            if (
                name.startswith("_")
                or name in self.SKIP_MODULES
            ):
                continue

            full_name = f"{package.__name__}.{name}"

            if full_name in self._visited_modules:
                continue

            self._visited_modules.add(full_name)

            try:

                module = importlib.import_module(
                    full_name
                )

            except Exception as exc:

                logger.warning(
                    "Failed importing %s: %s",
                    full_name,
                    exc,
                )

                continue

            self._register_module_tools(module)

            if hasattr(module, "__path__"):

                self._discover_package(module)

    # ---------------------------------------------------------

    def _register_module_tools(
        self,
        module: ModuleType,
    ) -> None:

        for _, cls in inspect.getmembers(
            module,
            inspect.isclass,
        ):

            if cls is BaseTool:
                continue

            if not issubclass(cls, BaseTool):
                continue

            if inspect.isabstract(cls):
                continue

            if cls in self._registered_classes:
                continue

            try:

                tool = cls()

                self.register(tool)

                self._registered_classes.add(cls)

            except Exception as exc:

                logger.warning(
                    "Failed registering %s: %s",
                    cls.__name__,
                    exc,
                )

    # ---------------------------------------------------------

    def register(
        self,
        tool: BaseTool,
    ) -> None:

        name = tool.metadata.name

        if name in self.tools:

            logger.warning(
                "Duplicate tool ignored: %s",
                name,
            )

            return

        logger.info(
            "Registering tool: %s",
            name,
        )

        self.tools[name] = tool

        #
        # Mike learns a new capability.
        #

        self.capabilities.register_tool(tool)

        logger.info(
            "Registered capability: %s",
            name,
        )

    # ---------------------------------------------------------

    def has(
        self,
        name: str,
    ) -> bool:

        return name in self.tools

    # ---------------------------------------------------------

    def get(
        self,
        name: str,
    ) -> BaseTool | None:

        return self.tools.get(name)

    # ---------------------------------------------------------

    def execute(
        self,
        tool_name: str,
        **kwargs,
    ):

        tool = self.get(tool_name)

        if tool is None:

            raise ValueError(
                f"Unknown tool: {tool_name}"
            )

        return tool.execute(**kwargs)

    # ---------------------------------------------------------

    def available(self) -> list[str]:

        return sorted(self.tools.keys())

    # ---------------------------------------------------------

    def capabilities_list(self):

        return self.capabilities.enabled()

    # ---------------------------------------------------------

    def reload(self) -> None:

        self.tools.clear()

        self.capabilities = CapabilityRegistry()

        self._visited_modules.clear()

        self._registered_classes.clear()

        self._discover_package(tools)