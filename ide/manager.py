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
        "VS Code is open but isn't talking to me. This is almost always "
        "Restricted Mode: if the folder is untrusted, VS Code silently "
        "disables extensions including mine. Click 'Trust' in the banner at "
        "the top (or Manage Workspace Trust), then reload VS Code and I'll "
        "connect. If it was only just installed, VS Code needs a restart to "
        "pick it up."
    )


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
