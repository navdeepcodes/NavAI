from __future__ import annotations

from tools.base_tool import BaseTool
from tools.tool_context import ToolContext
from tools.tool_metadata import ToolMetadata
from tools.tool_permission import Permission
from tools.tool_result import ToolResult

from tools.email import actions


class EmailTool(BaseTool):

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    @property
    def metadata(self) -> ToolMetadata:

        return ToolMetadata(

            name="email",

            description="Send and read emails.",

            category="email",

            tags=[

                "email",

                "gmail",

                "mail",

                "communication",

            ],

        )

    # ---------------------------------------------------------
    # Permission
    # ---------------------------------------------------------

    @property
    def permission(self) -> Permission:

        return Permission.EMAIL

    # ---------------------------------------------------------
    # Supported Actions
    # ---------------------------------------------------------

    @property
    def actions(self):

        return {

            "send_email": actions.send_email,

            "read_email": actions.read_email,

        }

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    def validate(
        self,
        action: str,
        **kwargs,
    ) -> bool:

        validators = {

            "send_email": lambda: (

                bool(kwargs.get("to"))

                and bool(kwargs.get("subject"))

                and kwargs.get("body") is not None

            ),

            "read_email": lambda: True,

        }

        validator = validators.get(action)

        return validator() if validator else False

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

                error=f"Unknown email action '{action}'.",

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