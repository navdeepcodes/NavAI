"""Approvals that last the session: "allow edits in this project", "always
allow this command".

A coding session is a string of small edits and the same few commands, run
again and again. Asked every time, a student approves ten cards to build one
small project, and a confirmation clicked through ten times stops being read.
The gate stays; the student can widen it -- knowingly and narrowly: edits under
one project's folder, or one exact command, until Mike restarts. Deleting,
stopping a process, sending mail and irreversible clicks are never covered,
and nothing outside the granted folder is.
"""
from __future__ import annotations

import os
from pathlib import Path

EDIT_TOOLS = frozenset({"edit_file", "multi_edit", "write_file", "write_files", "ide_apply_edit"})
COMMAND_TOOLS = frozenset({"run_command", "run_background"})

#: What marks a folder as a project's root, nearest first.
_MARKERS = (".git", "package.json", "pyproject.toml", "requirements.txt", "setup.py",
            "Cargo.toml", "go.mod", "pom.xml", "build.gradle", ".vscode")


def _key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _within(path: Path, root: Path) -> bool:
    p, r = _key(path), _key(root)
    return p == r or p.startswith(r.rstrip("\\/") + os.sep)


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


class SessionGrants:

    def __init__(self) -> None:
        self.roots: list[Path] = []
        self.commands: set[str] = set()

    # -- what an action touches -------------------------------------------
    @staticmethod
    def _paths(name: str, args: dict) -> list[Path]:
        from tools.filesystem.path_utils import resolve_path
        if name == "write_files":
            raw = [f.get("path") for f in (args.get("files") or []) if isinstance(f, dict)]
        else:
            raw = [args.get("path")]
        raw = [str(p) for p in raw if p and str(p).strip()]
        return [resolve_path(p) for p in raw]

    @staticmethod
    def _project_root(path: Path) -> Path | None:
        """The project a file belongs to: the connected editor's folder if
        it's inside it, else the nearest folder that looks like a project,
        else the file's own folder -- never a home folder or a whole drive."""
        root = None
        try:
            from ide import manager
            ws = manager.get_context().workspace_root if manager.is_connected() else ""
            if ws and _within(path, Path(ws)):
                root = Path(ws)
        except Exception:
            pass
        if root is None:
            for parent in [path.parent, *path.parent.parents]:
                if any((parent / m).exists() for m in _MARKERS):
                    root = parent
                    break
        root = root or path.parent
        home = Path.home()
        if _key(root) in (_key(home), _key(home.parent)) or root.parent == root:
            return None
        return root

    def _root_for(self, name: str, args: dict) -> Path | None:
        paths = self._paths(name, args)
        if not paths:
            return None
        root = self._project_root(paths[0])
        if root is None or not all(_within(p, root) for p in paths):
            return None
        return root

    @staticmethod
    def _command(args: dict) -> str:
        return " ".join(str(args.get("command") or "").split())

    # -- the three questions -----------------------------------------------
    def offer(self, name: str, args: dict) -> str:
        """The wider approval this action could be given, as the card's words
        -- or "" when it can't be widened."""
        if name in EDIT_TOOLS:
            root = self._root_for(name, args)
            return f"Allow edits in {root.name or root} this session" if root else ""
        if name in COMMAND_TOOLS:
            command = self._command(args)
            return f"Always allow “{_clip(command, 38)}” this session" if command else ""
        return ""

    def grant(self, name: str, args: dict) -> None:
        if name in EDIT_TOOLS:
            root = self._root_for(name, args)
            if root is not None and not any(_key(r) == _key(root) for r in self.roots):
                self.roots.append(root)
        elif name in COMMAND_TOOLS:
            command = self._command(args)
            if command:
                self.commands.add(command)

    def covers(self, name: str, args: dict) -> bool:
        if name in EDIT_TOOLS:
            paths = self._paths(name, args)
            return bool(paths) and all(any(_within(p, r) for r in self.roots) for p in paths)
        if name in COMMAND_TOOLS:
            return self._command(args) in self.commands
        return False
