"""The IDE-agnostic surface Mike talks to.

Only capabilities that actually exist today are described here. Adapters for
other editors implement the same two protocols; nothing above this layer knows
which editor is attached.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Diagnostic:
    file: str
    line: int
    column: int
    severity: str          # error | warning | info | hint
    message: str
    source: str = ""

    def describe(self) -> str:
        where = f"{self.file}:{self.line}"
        origin = f" [{self.source}]" if self.source else ""
        return f"{self.severity}{origin} at {where} — {self.message}"


@dataclass
class TerminalRun:
    """One command in the editor's terminal -- the student's own or one Mike
    started there -- with how it ended and the end of what it printed."""

    terminal: str
    command: str
    cwd: str = ""
    running: bool = False
    exit_code: int | None = None
    output: str = ""
    by_mike: bool = False
    started_at: float = 0.0
    ended_at: float = 0.0
    id: str = ""

    @property
    def failed(self) -> bool:
        return not self.running and self.exit_code not in (None, 0)

    def describe(self, lines: int = 30) -> str:
        who = "Mike ran" if self.by_mike else "They ran"
        if self.running:
            state = "still running"
        elif self.exit_code is None:
            state = "finished"
        else:
            state = f"exited with code {self.exit_code}"
        where = f" in {self.cwd}" if self.cwd else ""
        head = f"{who} `{self.command}`{where} (the {self.terminal!r} terminal): {state}."
        shown = "\n".join(self.output.splitlines()[-lines:]).strip()
        return head + (f" The end of its output:\n{shown}" if shown else " It printed nothing.")


@dataclass
class IDEContext:
    """A snapshot of what the user is looking at. Every field is optional —
    an editor with no file open is a normal state, not an error."""

    editor: str = ""                    # "VS Code"
    workspace_name: str = ""
    workspace_root: str = ""
    file_path: str = ""
    language: str = ""
    line: int = 0
    column: int = 0
    selection: str = ""
    selection_start_line: int = 0
    selection_end_line: int = 0
    open_files: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    updated_at: float = 0.0
    workspace_folders: list[str] = field(default_factory=list)
    #: The latest commands in the editor's terminals, oldest first.
    terminal: list[TerminalRun] = field(default_factory=list)
    #: The editor can run a command in its terminal and follow it for Mike.
    can_run_commands: bool = False
    window_id: str = ""

    @property
    def filename(self) -> str:
        return self.file_path.rsplit("/", 1)[-1] if self.file_path else ""

    def is_empty(self) -> bool:
        return not (self.file_path or self.workspace_root)

    def describe(self, terminal: str = "brief") -> str:
        """Short natural-language form for the model's system prompt. The
        terminal part "brief" (what's running, and a fresh failure), "full"
        (every recent command, with output) or "" (none)."""

        if self.is_empty():
            return ""

        bits: list[str] = [f"The user is working in {self.editor or 'their editor'}"]

        if self.workspace_name:
            # Where it is, too: without it the model guessed relative paths
            # for the project's files (measured: three wasted steps).
            root = f" ({self.workspace_root})" if self.workspace_root else ""
            bits.append(f"on the project “{self.workspace_name}”{root}")

        line = " ".join(bits) + "."
        out = [line]

        if self.file_path:
            where = f"Open file: {self.file_path}"
            if self.language:
                where += f" ({self.language})"
            if self.line:
                where += f", cursor on line {self.line}"
            out.append(where + ".")

        if self.selection.strip():
            snippet = self.selection.strip()
            if len(snippet) > 800:
                snippet = snippet[:800] + "\n…(truncated)"
            span = ""
            if self.selection_start_line:
                span = f" (lines {self.selection_start_line}-{self.selection_end_line})"
            out.append(f"Selected code{span}:\n{snippet}")

        errors = [d for d in self.diagnostics if d.severity == "error"]
        shown = errors[:5] or self.diagnostics[:5]
        if shown:
            out.append(
                "Problems the editor is reporting:\n"
                + "\n".join(f"- {d.describe()}" for d in shown)
            )

        said = self.describe_terminal(brief=terminal != "full") if terminal else ""
        if said:
            out.append(said)

        return "\n".join(out)

    #: A finished command is news for this long; after that it's history.
    RECENT_SECONDS = 600

    def describe_terminal(self, brief: bool = False, now: float | None = None) -> str:
        """What's running in the editor's terminals, and how the latest command
        ended. Brief (each turn): what's running, and the last command only
        if it failed lately, with the end of its output -- the error is
        usually there. Full (asked for): every recent command."""
        import time
        now = time.time() if now is None else now
        if not brief:
            if not self.terminal:
                return ""
            return "Their editor's terminal, oldest first:\n" + "\n\n".join(
                run.describe() for run in self.terminal)
        out = []
        running = [r for r in self.terminal if r.running]
        if running:
            out.append("Running in their editor's terminal: " + "; ".join(
                f"`{r.command}`" + (" (Mike started it)" if r.by_mike else "") for r in running) + ".")
        finished = [r for r in self.terminal if not r.running]
        last = finished[-1] if finished else None
        if last and last.failed and now - (last.ended_at or now) < self.RECENT_SECONDS:
            out.append(last.describe(lines=8))
        return "\n".join(out)


@runtime_checkable
class IDEContextProvider(Protocol):
    def is_connected(self) -> bool: ...
    def get_context(self) -> IDEContext: ...
    def get_diagnostics(self) -> list[Diagnostic]: ...


@runtime_checkable
class IDEController(Protocol):
    def open_file(self, path: str, line: int | None = None) -> dict[str, Any]: ...
    def reveal_location(self, path: str, line: int) -> dict[str, Any]: ...
    def apply_edit(self, path: str, new_text: str, replace_selection: bool) -> dict[str, Any]: ...
