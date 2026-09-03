"""Editor-native actions.

Filesystem work stays with the filesystem tool — this covers only what has to
happen inside the editor itself: navigating the user's view and editing the
live document they have open.
"""
from __future__ import annotations

from ide import manager
from tools.base_tool import BaseTool
from tools.tool_context import ToolContext
from tools.tool_metadata import ToolMetadata
from tools.tool_permission import Permission
from tools.tool_result import ToolResult


class IDETool(BaseTool):

    @property
    def metadata(self) -> ToolMetadata:

        return ToolMetadata(
            name="ide",
            description=(
                "Read what the user is looking at in their editor and act "
                "inside it — open files, jump to a line, or edit the open "
                "document."
            ),
            category="ide",
            tags=["ide", "editor", "vscode", "code"],
        )

    @property
    def permission(self) -> Permission:

        return Permission.FILESYSTEM

    @property
    def actions(self):

        return {
            "get_context": self._get_context,
            "open_file": self._open_file,
            "reveal_location": self._reveal_location,
            "apply_edit": self._apply_edit,
        }

    def validate(self, action: str, **kwargs) -> bool:

        validators = {
            "get_context": lambda: True,
            "open_file": lambda: bool(kwargs.get("path")),
            "reveal_location": lambda: bool(kwargs.get("path")),
            "apply_edit": lambda: bool(kwargs.get("path")) and "text" in kwargs,
        }

        validator = validators.get(action)
        return validator() if validator else False

    def execute(self, action: str, context: ToolContext, **kwargs) -> ToolResult:

        handler = self.actions.get(action)

        if handler is None:
            return ToolResult(
                success=False,
                tool=self.metadata.name,
                action=action,
                error=f"Unknown ide action '{action}'.",
            )

        try:
            message, ok = handler(**kwargs)

            return ToolResult(
                success=ok,
                tool=self.metadata.name,
                action=action,
                message=message if ok else "",
                error=None if ok else message,
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                tool=self.metadata.name,
                action=action,
                error=str(exc),
            )

    # ── Handlers ─────────────────────────────────────────────
    # Each returns (message, ok).

    def _get_context(self, **kwargs) -> tuple[str, bool]:

        if not manager.is_connected():
            return (
                "No editor is connected. The user may not have VS Code open, "
                "or the Mike extension isn't running.",
                False,
            )

        described = manager.describe()
        return (described or "An editor is connected but nothing is open in it.", True)

    def _open_file(self, path: str, line: int | None = None, **kwargs) -> tuple[str, bool]:

        result = manager.open_file(path, line)

        if not result.get("ok"):
            return (result.get("error") or "Could not open that in the editor.", False)

        where = f"{path}:{line}" if line else path
        return (f"Opened {where} in the editor.", True)

    def _reveal_location(self, path: str, line: int = 1, **kwargs) -> tuple[str, bool]:

        result = manager.reveal_location(path, int(line))

        if not result.get("ok"):
            return (result.get("error") or "Could not reveal that location.", False)

        return (f"Revealed {path}:{line} in the editor.", True)

    def _apply_edit(
        self,
        path: str,
        text: str,
        replace_selection: bool = False,
        **kwargs,
    ) -> tuple[str, bool]:

        result = manager.apply_edit(path, text, bool(replace_selection))

        if not result.get("ok"):
            return (result.get("error") or "The edit could not be applied.", False)

        target = "the selection" if replace_selection else path
        return (f"Applied the edit to {target}.", True)
