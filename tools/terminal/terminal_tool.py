from __future__ import annotations

from tools.base_tool import BaseTool
from tools.tool_context import ToolContext
from tools.tool_metadata import ToolMetadata
from tools.tool_permission import Permission
from tools.tool_result import ToolResult

from tools.terminal.actions import run, run_background


class TerminalTool(BaseTool):

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    @property
    def metadata(self) -> ToolMetadata:

        return ToolMetadata(

            name="terminal",

            description="Execute terminal commands.",

            category="terminal",

            tags=[

                "terminal",

                "shell",

                "command",

                "cli",

            ],

        )

    # ---------------------------------------------------------
    # Permission
    # ---------------------------------------------------------

    @property
    def permission(self) -> Permission:

        return Permission.TERMINAL

    # ---------------------------------------------------------
    # Supported Actions
    # ---------------------------------------------------------

    @property
    def actions(self):

        return {

            "run": self._run,

            "run_background": self._run_background,

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

            "run": lambda: bool(
                kwargs.get("command")
            ),

            "run_background": lambda: bool(
                kwargs.get("command")
            ),

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

                error=f"Unknown terminal action '{action}'.",

            )

        try:

            result = handler(**kwargs)

            return ToolResult(

                success=True,

                tool=self.metadata.name,

                action=action,

                message="Command executed successfully.",

                data={

                    "output": result

                },

            )

        except Exception as exc:

            return ToolResult(

                success=False,

                tool=self.metadata.name,

                action=action,

                error=str(exc),

            )

    # ---------------------------------------------------------
    # Action Handlers
    # ---------------------------------------------------------

    def _run(
        self,
        command: str,
        cwd: str | None = None,
        **kwargs,
    ):

        return run(command, cwd=cwd)

    def _run_background(
        self,
        command: str,
        cwd: str | None = None,
        **kwargs,
    ):

        return run_background(command, cwd=cwd)