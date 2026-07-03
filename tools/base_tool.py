from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from tools.tool_context import ToolContext
from tools.tool_metadata import ToolMetadata
from tools.tool_permission import Permission
from tools.tool_result import ToolResult


class BaseTool(ABC):
    """
    Base class for every tool.

    A tool groups related actions together.

    Example:

        BrowserTool
            - open_browser
            - open_url
            - search

        FilesystemTool
            - create_file
            - write_file
            - move
            - copy
    """

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Static metadata describing this tool."""
        raise NotImplementedError

    # ---------------------------------------------------------
    # Permission
    # ---------------------------------------------------------

    @property
    @abstractmethod
    def permission(self) -> Permission:
        """Permission required before execution."""
        raise NotImplementedError

    # ---------------------------------------------------------
    # Supported Actions
    # ---------------------------------------------------------

    @property
    @abstractmethod
    def actions(self) -> dict[str, Callable]:
        """
        Mapping of action names to handler methods.

        Example:

        {
            "open_url": self._open_url,
            "search": self._search,
        }
        """
        raise NotImplementedError

    # ---------------------------------------------------------
    # Execute
    # ---------------------------------------------------------

    @abstractmethod
    def execute(
        self,
        action: str,
        context: ToolContext,
        **kwargs,
    ) -> ToolResult:
        """
        Execute an action supported by this tool.
        """
        raise NotImplementedError

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    def validate(
        self,
        action: str,
        **kwargs,
    ) -> bool:
        """
        Validate action arguments.

        Override in subclasses when required.
        """
        return True

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------

    def cleanup(self) -> None:
        """
        Optional cleanup after execution.
        """
        return

    # ---------------------------------------------------------
    # Health Check
    # ---------------------------------------------------------

    def health_check(self) -> bool:
        """
        Return True if the tool is healthy.
        """
        return True