from __future__ import annotations

from tools.base_tool import BaseTool
from tools.tool_context import ToolContext
from tools.tool_metadata import ToolMetadata
from tools.tool_permission import Permission
from tools.tool_result import ToolResult

from tools.filesystem import actions


class FilesystemTool(BaseTool):

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    @property
    def metadata(self) -> ToolMetadata:

        return ToolMetadata(

            name="filesystem",

            description="Manage files and directories.",

            category="filesystem",

            tags=[

                "filesystem",

                "files",

                "folders",

                "storage",

                "directory",

            ],

        )

    # ---------------------------------------------------------
    # Permission
    # ---------------------------------------------------------

    @property
    def permission(self) -> Permission:

        return Permission.FILESYSTEM

    # ---------------------------------------------------------
    # Supported Actions
    # ---------------------------------------------------------

    @property
    def actions(self):

        return {

            "create_folder": actions.create_folder,

            "create_file": actions.create_file,

            "read_file": actions.read_file,

            "write_file": actions.write_file,

            "append_file": actions.append_file,

            "list_directory": actions.list_directory,

            "delete": actions.delete,

            "rename": actions.rename,

            "move": actions.move,

            "copy": actions.copy,

            "open_path": actions.open_path,

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

            "create_folder": lambda: bool(kwargs.get("path")),

            "create_file": lambda: bool(kwargs.get("path")),

            "read_file": lambda: bool(kwargs.get("path")),

            "write_file": lambda: (
                bool(kwargs.get("path"))
                and kwargs.get("content") is not None
            ),

            "append_file": lambda: (
                bool(kwargs.get("path"))
                and kwargs.get("content") is not None
            ),

            "list_directory": lambda: bool(kwargs.get("path")),

            "delete": lambda: bool(kwargs.get("path")),

            "rename": lambda: (
                bool(kwargs.get("source"))
                and bool(kwargs.get("new_name"))
            ),

            "move": lambda: (
                bool(kwargs.get("source"))
                and bool(kwargs.get("destination"))
            ),

            "copy": lambda: (
                bool(kwargs.get("source"))
                and bool(kwargs.get("destination"))
            ),

            "open_path": lambda: bool(kwargs.get("path")),

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

                error=f"Unknown filesystem action '{action}'.",

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