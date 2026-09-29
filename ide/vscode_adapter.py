"""VS Code adapter.

Everything VS Code-specific lives here: the shape of the payload its extension
sends, and the command names it understands. A Cursor or JetBrains adapter
would sit beside this file implementing the same contracts.
"""
from __future__ import annotations

from typing import Any

from ide.bridge import IDEBridge
from ide.contracts import Diagnostic, IDEContext, TerminalRun

EDITOR_NAME = "VS Code"


class VSCodeAdapter:

    def __init__(self, bridge: IDEBridge) -> None:
        self._bridge = bridge

    # ── Context ──────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self._bridge.is_connected()

    def get_context(self) -> IDEContext:
        return self._context(self._bridge.raw_context())

    def _context(self, raw: dict) -> IDEContext:
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
            workspace_folders=list(workspace.get("folders") or []),
            terminal=self._parse_runs(raw.get("terminal") or []),
            can_run_commands=bool(raw.get("canRunCommands")),
            window_id=str(raw.get("windowId") or ""),
        )

    @staticmethod
    def _parse_runs(items: list[dict]) -> list[TerminalRun]:
        runs: list[TerminalRun] = []
        for item in items:
            try:
                code = item.get("exitCode")
                runs.append(TerminalRun(
                    terminal=str(item.get("terminal") or ""),
                    command=str(item.get("command") or ""),
                    cwd=str(item.get("cwd") or ""),
                    running=bool(item.get("running")),
                    exit_code=int(code) if isinstance(code, (int, float)) else None,
                    output=str(item.get("output") or ""),
                    by_mike=bool(item.get("byMike")),
                    started_at=float(item.get("startedAt") or 0.0),
                    ended_at=float(item.get("endedAt") or 0.0),
                    id=str(item.get("id") or ""),
                ))
            except (TypeError, ValueError):
                continue
        return runs

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

    def open_file(self, path: str, line: int | None = None, window: str = "") -> dict[str, Any]:
        return self._bridge.send_command(
            "openFile", {"path": path, "line": line}, window_id=window
        )

    def reveal_location(self, path: str, line: int) -> dict[str, Any]:
        return self._bridge.send_command(
            "revealLocation", {"path": path, "line": line}
        )

    def read_text(self, path: str) -> dict[str, Any]:
        """The open document's text, unsaved changes included."""
        return self._bridge.send_command("readText", {"path": path}, timeout=5.0)

    def replace_range(self, path: str, start: tuple[int, int], end: tuple[int, int],
                      old: str, new: str) -> dict[str, Any]:
        """Replace [start, end) -- (line, UTF-16 column), 0-based -- if it still
        holds `old`; saved, undoable, and with the file's problems after."""
        return self._bridge.send_command(
            "replaceRange",
            {"path": path, "startLine": start[0], "startChar": start[1],
             "endLine": end[0], "endChar": end[1], "old": old, "text": new},
            timeout=20.0,
        )

    # ── The terminal ─────────────────────────────────────────

    def context_of(self, raw: dict) -> IDEContext:
        """One window's snapshot (from the bridge's live_contexts) as an IDEContext."""
        return self._context(raw)

    def run_in_terminal(self, command: str, cwd: str, name: str,
                        shell: tuple[str, list[str]] | None, wait: float,
                        window: str = "") -> dict[str, Any]:
        """Start `command` in a terminal the student can see, and follow it:
        back when it ends or after `wait` seconds, with what it printed. The
        window it ran in comes back as "window" -- the run lives there."""
        window = window or self._bridge.preferred_window_id()
        params: dict[str, Any] = {"command": command, "cwd": cwd, "name": name,
                                  "waitMs": int(wait * 1000)}
        if shell:
            params["shellPath"], params["shellArgs"] = shell[0], list(shell[1])
        # The shell needs a few seconds to come up the first time.
        result = self._bridge.send_command("runInTerminal", params, timeout=wait + 20.0,
                                           window_id=window)
        return {**result, "window": window}

    def run_output(self, window: str, run_id: str) -> dict[str, Any]:
        return self._bridge.send_command("runOutput", {"runId": run_id}, timeout=5.0,
                                         window_id=window)

    def stop_run(self, window: str, run_id: str) -> dict[str, Any]:
        return self._bridge.send_command("stopRun", {"runId": run_id}, timeout=10.0,
                                         window_id=window)

    def problems(self, paths: list[str], wait: float, window: str = "") -> dict[str, Any]:
        """What the editor's own checkers say about these files, each opened
        in a tab behind the student's so they're checked at all."""
        return self._bridge.send_command("problems", {"paths": paths, "waitMs": int(wait * 1000)},
                                         timeout=wait + 8.0, window_id=window)

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
