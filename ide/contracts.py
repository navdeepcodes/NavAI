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

    @property
    def filename(self) -> str:
        return self.file_path.rsplit("/", 1)[-1] if self.file_path else ""

    def is_empty(self) -> bool:
        return not (self.file_path or self.workspace_root)

    def describe(self) -> str:
        """Short natural-language form for the model's system prompt."""

        if self.is_empty():
            return ""

        bits: list[str] = [f"The user is working in {self.editor or 'their editor'}"]

        if self.workspace_name:
            bits.append(f"on the project “{self.workspace_name}”")

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
