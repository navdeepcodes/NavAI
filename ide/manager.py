"""Single entry point the rest of Mike uses to reach whatever editor is attached.

Nothing outside ide/ imports an adapter directly, so adding another editor
later means adding a module here — not touching the brain, the tools, or the UI.
"""
from __future__ import annotations

import os

from ide.bridge import IDEBridge
from ide.contracts import Diagnostic, IDEContext
from ide.vscode_adapter import VSCodeAdapter
from logs.logger import logger

_bridge = IDEBridge()
_adapters = [VSCodeAdapter(_bridge)]

_started = False


def start() -> bool:
    """Begin listening for an editor. Safe to call more than once."""

    global _started

    if _started:
        return True

    _started = _bridge.start()
    return _started


def stop() -> None:
    global _started

    if _started:
        _bridge.stop()
        _started = False


def active_adapter():
    """The first adapter reporting a live editor, or None."""

    for adapter in _adapters:
        if adapter.is_connected():
            return adapter
    return None


def is_connected() -> bool:
    return active_adapter() is not None


def get_context() -> IDEContext:
    adapter = active_adapter()
    return adapter.get_context() if adapter else IDEContext()


def get_diagnostics() -> list[Diagnostic]:
    adapter = active_adapter()
    return adapter.get_diagnostics() if adapter else []


def describe() -> str:
    """Prompt-ready description, empty when no editor is attached."""

    return get_context().describe()


# ── Control ──────────────────────────────────────────────────

def _not_connected_reason() -> str:
    """Why the editor isn't reachable, in terms the user can act on.

    "No editor is connected" is true and useless -- it gives someone whose
    VS Code is open, with the extension installed, nothing to do. There are
    only a few real causes, and they have different fixes, so the message
    names the one that actually applies.

    Restricted Mode is called out first because it is the one that looks
    least like a problem: VS Code is running, the extension is installed and
    listed, and it simply never activates, because an untrusted folder
    disables extensions silently. That cost a long debugging session here --
    everything appeared correct and nothing connected -- and a user hitting
    it has no reason to suspect a trust setting.
    """
    from ide.install import find_vscode_cli, already_installed

    cli = find_vscode_cli()
    if cli is None:
        return (
            "I can't see VS Code on this machine. If it's installed, open a "
            "file in it once and I'll pick it up."
        )
    if not already_installed(cli):
        return (
            "VS Code is here but my editor extension isn't installed yet. "
            "I can install it for you -- just ask."
        )
    return (
        "VS Code is in Restricted Mode, so it has switched my extension off "
        "along with all the others — that's why I can't see your editor. "
        "Click Trust in the yellow bar at the top of VS Code (or the "
        "'Restricted Mode' button in its bottom-left corner), and I'll "
        "connect straight away. Tell the user this in your reply; they "
        "cannot fix it without being told. If it was only just installed, "
        "VS Code needs restarting once instead."
    )


def connection_hint() -> str | None:
    """A line worth volunteering when Mike is about to do editor work.

    Told, rather than discovered. Restricted Mode is the one failure here
    that looks like nothing is wrong: VS Code is open, the extension is
    installed and listed, and it simply never runs -- VS Code's own trust
    screen says "15 extensions are disabled or have limited functionality",
    which the user never sees unless they go looking. Waiting for a command
    to fail first means the user's first experience of coding help is it
    not working for no visible reason.

    Returns None when the editor is connected, which is the common case, so
    a working setup never pays for this.
    """
    if is_connected():
        return None
    return _not_connected_reason()


def _require_adapter():
    adapter = active_adapter()
    if adapter is None:
        return None, {"ok": False, "error": _not_connected_reason()}
    return adapter, None


def open_file(path: str, line: int | None = None) -> dict:
    adapter, failure = _require_adapter()
    if failure:
        return failure
    return adapter.open_file(path, line)


def reveal_location(path: str, line: int) -> dict:
    adapter, failure = _require_adapter()
    if failure:
        return failure
    return adapter.reveal_location(path, line)


def apply_edit(path: str, new_text: str, replace_selection: bool = False) -> dict:
    adapter, failure = _require_adapter()
    if failure:
        return failure
    return adapter.apply_edit(path, new_text, replace_selection)


# ── The editor's text is the truth ───────────────────────────
#
# A file open in the editor may hold unsaved changes. Read from disk and
# written back, Mike's edit was made to the older text, and the editor then had
# two versions of the file -- the student's unsaved work, or Mike's change, was
# lost. So a file open in the connected editor is read from the editor and
# edited through it: the edit lands in the student's buffer, is saved, and
# Ctrl+Z undoes it.

def _same_file(a: str, b: str) -> bool:
    """One file, however it's spelled. Windows gives the same folder two
    names -- measured: the editor had C:\\Users\\THRISH~1\\... open while Mike
    resolved it to C:\\Users\\Thrisha M C\\... -- so different spellings are
    compared by the file itself."""
    import os
    if os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b)):
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _editor_holding(path: str):
    """(adapter, the path as the editor knows it) when a connected editor has
    the file open; (None, "") otherwise. Commands use the editor's spelling."""
    adapter = active_adapter()
    if adapter is None or not hasattr(adapter, "read_text"):
        return None, ""
    for open_path in adapter.get_context().open_files:
        if _same_file(path, open_path):
            return adapter, open_path
    return None, ""


def editor_text(path: str) -> str | None:
    """The file's text as the editor has it right now (with \\n line endings),
    or None when it isn't open in a connected editor."""
    adapter, where = _editor_holding(path)
    if adapter is None:
        return None
    try:
        result = adapter.read_text(where)
    except Exception:
        return None
    if not result.get("ok"):
        return None
    return str(result.get("text") or "").replace("\r\n", "\n")


def replace_in_editor(path: str, start: tuple[int, int], end: tuple[int, int],
                      old: str, new: str) -> dict | None:
    """Apply one replacement through the editor. None when no connected editor
    holds the file (the caller writes the disk instead)."""
    adapter, where = _editor_holding(path)
    if adapter is None:
        return None
    try:
        return adapter.replace_range(where, start, end, old, new)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Opening things, where the student can see them ───────────
#
# Through VS Code's own program, not its code.cmd: a path the model wrote,
# handed to a .cmd, would be read by cmd.exe, where a "&" in it starts another
# command. Code.exe with a path is how Explorer's "Open with Code" does it:
# an already-running VS Code takes the request -- the window that has the
# folder open comes to the front, or a new one opens.

#: Extra arguments for every Code.exe start. Empty for students; a test points
#: them at a separate profile so the real VS Code is left alone.
EXTRA_ARGS: list[str] = []


def _code_program() -> str | None:
    from pathlib import Path

    from ide.install import find_vscode_cli
    cli = find_vscode_cli()
    if not cli:
        return None
    exe = Path(cli).resolve().parent.parent / ("Code.exe" if os.name == "nt" else "code")
    return str(exe) if exe.is_file() else None


def _start_code(args: list[str]) -> dict:
    import subprocess

    from hostplatform.processes import NO_WINDOW
    program = _code_program()
    if program is None:
        return {"ok": False, "error": "VS Code isn't installed on this computer, or I can't find it."}
    try:
        subprocess.Popen([program, *EXTRA_ARGS, *args], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=NO_WINDOW)
    except OSError as exc:
        return {"ok": False, "error": f"VS Code wouldn't start: {exc}"}
    return {"ok": True}


def _within(path: str, root: str) -> bool:
    if not root:
        return False
    try:
        full, base = (os.path.normcase(os.path.abspath(p)) for p in (path, root))
        return os.path.commonpath([full, base]) == base
    except ValueError:          # different drives
        return False


def _window_for(path: str) -> IDEContext | None:
    """The connected window whose project holds `path` -- the student's
    current one when several do, or when none does."""
    adapter = active_adapter()
    if adapter is None or not hasattr(adapter, "context_of"):
        return None
    windows = [adapter.context_of(raw) for raw in _bridge.live_contexts()]
    for ctx in windows:
        if any(_within(path, root) for root in (ctx.workspace_folders or [ctx.workspace_root])):
            return ctx
    return windows[0] if windows else None


#: How long opening a project waits for its window to connect: a cold VS Code
#: on the target laptop took 14.5s to open a folder and connect.
FOLDER_CONNECT_SECONDS = 20.0


def _await_window(folder: str) -> bool:
    """Wait for the window showing `folder` to connect, so what Mike does next
    in that project -- the files he writes, the server he starts -- lands in
    it, not in whichever window was connected before."""
    import time
    deadline = time.monotonic() + FOLDER_CONNECT_SECONDS
    while time.monotonic() < deadline:
        for raw in _bridge.live_contexts():
            workspace = raw.get("workspace") or {}
            if any(_same_file(folder, root) for root in (workspace.get("folders") or [])):
                return True
        time.sleep(0.5)
    return False


def _raise_window(ctx: IDEContext | None) -> None:
    """Bring the VS Code window showing this project to the front. Opening a
    file there doesn't: the student asked Mike from somewhere else and saw
    nothing happen."""
    if os.name != "nt":
        return
    try:
        from hostplatform.foreground import bring_to_front, windows_of
        windows = windows_of("Code.exe")
        if not windows:
            return
        name = (ctx.workspace_name if ctx else "") or ""
        # VS Code titles its windows "file - project - Visual Studio Code".
        hwnd = next((h for h, title in windows
                     if name and (f" - {name} - " in title or title.startswith(f"{name} - "))),
                    windows[0][0])
        bring_to_front(hwnd)
        _point_at(hwnd)
    except Exception:
        logger.debug("Couldn't bring VS Code to the front.", exc_info=True)


def _point_at(hwnd: int) -> None:
    """Show where VS Code came forward (the guide's nib, if it's running)."""
    try:
        import win32gui

        from computer import attention
        if not attention.active():
            return
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)

        class _Where:
            x, y, width, height = left, top, right - left, bottom - top
        attention.window(_Where, "Opening in VS Code")
    except Exception:
        pass


def open_in_editor(path: str, line: int | None = None) -> dict:
    """Show a file (at a line) or a whole project folder in VS Code, in front.

    A folder opens in its own window, or brings forward the one that already
    has it. A file opens in the window whose project holds it, through the
    extension when it's connected, and VS Code comes to the front; with no
    extension, VS Code's own program opens it."""
    full = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(full):
        return {"ok": False, "error": f"There's nothing at {full} to open."}
    if os.path.isdir(full):
        seen_an_editor = _bridge.ever_connected()
        started = _start_code([full])
        if started.get("ok"):
            started.update(kind="folder", path=full,
                           connected=seen_an_editor and _await_window(full))
        return started
    ctx = _window_for(full) if is_connected() else None
    adapter = active_adapter()
    if ctx is not None and adapter is not None:
        result = adapter.open_file(full, line, window=ctx.window_id)
        if result.get("ok"):
            _raise_window(ctx)
            return {"ok": True, "kind": "file", "path": full, "project": ctx.workspace_name}
    started = _start_code(["--goto", f"{full}:{line}" if line else full])
    if started.get("ok"):
        started.update(kind="file", path=full)
    return started


# ── The terminal ─────────────────────────────────────────────

def run_in_terminal(command: str, cwd: str, wait: float = 4.0) -> dict | None:
    """Run `command` in a terminal in the student's VS Code -- the one whose
    project holds `cwd` -- where they can watch it and stop it themselves,
    and follow it for Mike. None when that can't be done (no editor, an older
    extension, a terminal VS Code can't follow): run it the hidden way then."""
    ctx = _window_for(cwd) if is_connected() else None
    adapter = active_adapter()
    if ctx is None or adapter is None or not ctx.can_run_commands \
            or not hasattr(adapter, "run_in_terminal"):
        return None
    from hostplatform import processes
    # The terminal's tab: the command, shortened at a word where it's long.
    words = " ".join(command.split())
    name = "Mike: " + (words if len(words) <= 32 else words[:32].rsplit(" ", 1)[0] + " …")
    try:
        result = adapter.run_in_terminal(command, cwd, name, processes.editor_shell(), wait,
                                         window=ctx.window_id)
    except Exception:
        logger.exception("Running in the editor's terminal failed.")
        return None
    if not result.get("ok"):
        logger.info("The editor couldn't run %r (%s); running it out of sight.",
                    command, result.get("error"))
        return None
    return result


def run_output(window: str, run_id: str) -> dict:
    adapter = active_adapter()
    if adapter is None or not hasattr(adapter, "run_output"):
        return {"ok": False, "error": "VS Code isn't connected to Mike any more."}
    return adapter.run_output(window, run_id)


def stop_run(window: str, run_id: str) -> dict:
    adapter = active_adapter()
    if adapter is None or not hasattr(adapter, "stop_run"):
        return {"ok": False, "error": "VS Code isn't connected to Mike any more."}
    return adapter.stop_run(window, run_id)


def terminal_report() -> str:
    """Every recent command in the editor's terminals, with its output."""
    return get_context().describe_terminal(brief=False)


# ── The editor's own checks ──────────────────────────────────

def problems_for(paths: list[str], wait: float = 2.5) -> dict[str, dict] | None:
    """What VS Code's own checkers -- the TypeScript server, Pylance, the JSON
    and CSS checkers -- say about files Mike just wrote: {path: {"reported",
    "problems"}}, for the files inside a connected project. None when there's
    nothing to ask (no editor, files elsewhere, an older extension)."""
    if not paths or not is_connected():
        return None
    ctx = _window_for(paths[0])
    adapter = active_adapter()
    if ctx is None or adapter is None or not hasattr(adapter, "problems"):
        return None
    roots = ctx.workspace_folders or [ctx.workspace_root]
    inside = [p for p in paths if any(_within(p, r) for r in roots)]
    if not inside:
        return None
    try:
        result = adapter.problems(inside, wait, window=ctx.window_id)
    except Exception:
        logger.exception("Asking the editor for problems failed.")
        return None
    if not result.get("ok"):
        return None
    out: dict[str, dict] = {}
    for item in result.get("files") or []:
        mine = next((p for p in inside if _same_file(p, str(item.get("path") or ""))), None)
        if mine is not None:
            out[mine] = {"reported": bool(item.get("reported")),
                         "problems": list(item.get("problems") or [])}
    return out or None


def set_ask_handler(handler) -> None:
    """Who answers "Mike: Ask about this" from the editor. Called on the
    bridge's thread; the handler hands the question to its own."""
    _bridge.on_ask = handler
