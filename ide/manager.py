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

def _require_adapter():
    adapter = active_adapter()
    if adapter is None:
        return None, {"ok": False, "error": "No editor is connected to Mike right now."}
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
