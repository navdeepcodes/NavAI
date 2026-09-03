"""VS Code adapter.

Everything VS Code-specific lives here: the shape of the payload its extension
sends, and the command names it understands. A Cursor or JetBrains adapter
would sit beside this file implementing the same contracts.
"""
from __future__ import annotations

from typing import Any

from ide.bridge import IDEBridge
from ide.contracts import Diagnostic, IDEContext

EDITOR_NAME = "VS Code"


class VSCodeAdapter:

    def __init__(self, bridge: IDEBridge) -> None:
        self._bridge = bridge

    # ── Context ──────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self._bridge.is_connected()

    def get_context(self) -> IDEContext:
        raw = self._bridge.raw_context()

        if not raw:
            return IDEContext()

        editor = raw.get("editor") or {}
        workspace = raw.get("workspace") or {}
        selection = raw.get("selection") or {}
        cursor = raw.get("cursor") or {}

        return IDEContext(
            editor=raw.get("editorName") or EDITOR_NAME,
            workspace_name=workspace.get("name") or "",
            workspace_root=workspace.get("root") or "",
            file_path=editor.get("path") or "",
            language=editor.get("language") or "",
            line=int(cursor.get("line") or 0),
            column=int(cursor.get("column") or 0),
            selection=selection.get("text") or "",
            selection_start_line=int(selection.get("startLine") or 0),
            selection_end_line=int(selection.get("endLine") or 0),
            open_files=list(raw.get("openFiles") or []),
            diagnostics=self._parse_diagnostics(raw.get("diagnostics") or []),
            updated_at=float(raw.get("timestamp") or 0.0),
        )

    def get_diagnostics(self) -> list[Diagnostic]:
        return self.get_context().diagnostics

    @staticmethod
    def _parse_diagnostics(items: list[dict]) -> list[Diagnostic]:
        parsed: list[Diagnostic] = []

        for item in items:
            try:
                parsed.append(
                    Diagnostic(
                        file=item.get("file") or "",
                        line=int(item.get("line") or 0),
                        column=int(item.get("column") or 0),
                        severity=(item.get("severity") or "info").lower(),
                        message=item.get("message") or "",
                        source=item.get("source") or "",
                    )
                )
            except Exception:
                continue

        return parsed

    # ── Control ──────────────────────────────────────────────

    def open_file(self, path: str, line: int | None = None) -> dict[str, Any]:
        return self._bridge.send_command(
            "openFile", {"path": path, "line": line}
        )

    def reveal_location(self, path: str, line: int) -> dict[str, Any]:
        return self._bridge.send_command(
            "revealLocation", {"path": path, "line": line}
        )

    def apply_edit(
        self,
        path: str,
        new_text: str,
        replace_selection: bool = False,
    ) -> dict[str, Any]:
        return self._bridge.send_command(
            "applyEdit",
            {
                "path": path,
                "text": new_text,
                "replaceSelection": replace_selection,
            },
            timeout=20.0,
        )
