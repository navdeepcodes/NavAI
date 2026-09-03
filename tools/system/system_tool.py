from __future__ import annotations

from tools.base_tool import BaseTool
from tools.tool_context import ToolContext
from tools.tool_metadata import ToolMetadata
from tools.tool_permission import Permission
from tools.tool_result import ToolResult

from tools.system import actions


class SystemTool(BaseTool):

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    @property
    def metadata(self) -> ToolMetadata:

        return ToolMetadata(

            name="system",

            description="Control the operating system.",

            category="system",

            tags=[

                "system",

                "shutdown",

                "restart",

                "sleep",

                "lock",

            ],

        )

    # ---------------------------------------------------------
    # Permission
    # ---------------------------------------------------------

    @property
    def permission(self) -> Permission:

        return Permission.SYSTEM

    # ---------------------------------------------------------
    # Supported Actions
    # ---------------------------------------------------------

    @property
    def actions(self):

        return {

            "open_application": actions.open_application,

            "lock": actions.lock,

            "sleep": actions.sleep,

            "shutdown": actions.shutdown,

            "restart": actions.restart,

        }

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    def validate(
        self,
        action: str,
        **kwargs,
    ) -> bool:

        return action in self.actions

    # ---------------------------------------------------------
    # Execute
    # ---------------------------------------------------------

    def execute(
        self,
        action: str,
        context: ToolContext,
        **kwargs,
    ) -> ToolResult:

        handler = self.actions.get(action)

        if handler is None:

            return ToolResult(

                success=False,

                tool=self.metadata.name,

                action=action,

                error=f"Unknown system action '{action}'.",

            )

        try:

            result = handler(**kwargs)

            return ToolResult(

                success=True,

                tool=self.metadata.name,

                action=action,

                message=str(result),

            )

        except Exception as exc:

            return ToolResult(

                success=False,

                tool=self.metadata.name,

                action=action,

                error=str(exc),

            )