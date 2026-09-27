"""Single entry point the rest of Mike uses to reach whatever editor is attached.

Nothing outside ide/ imports an adapter directly, so adding another editor
later means adding a module here — not touching the brain, the tools, or the UI.
"""
from __future__ import annotations

from ide.bridge import IDEBridge
from ide.contracts import Diagnostic, IDEContext
from ide.vscode_adapter import VSCodeAdapter

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


def set_ask_handler(handler) -> None:
    """Who answers "Mike: Ask about this" from the editor. Called on the
    bridge's thread; the handler hands the question to its own."""
    _bridge.on_ask = handler
