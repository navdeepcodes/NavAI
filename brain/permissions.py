"""What Mike is allowed to do — decided by the person, enforced by the runtime.

Each ability groups the tools that make it possible. Turning one off in
Settings → Permissions does two things, so it can't be talked around:

  1. the tools disappear from what the model is offered at all, so it never
     plans with them, and
  2. a call to one anyway (a stale plan, a confused model) is refused before
     anything runs, with a message saying the user turned it off.

Everything is on by default except working with code, which is offered
when the user turns it on or has their code editor connected: its sixteen
tools were a quarter of the prompt every conversation carried (~2,000 of
~8,300 tokens), read at ~56 tokens/s on the target laptop and confusing a
small model's choice between the everyday tools. This narrows what Mike does;
it never widens what he could do without asking. Confirmation for
destructive actions stays exactly as it is, whatever is switched on here.
"""
from __future__ import annotations

#: key -> (title, description, tool names)
ABILITIES: dict[str, tuple[str, str, frozenset[str]]] = {
    "apps": (
        "Use apps for you",
        "Click, type and switch between windows in other apps.",
        frozenset({"see_ui", "click_element", "type_text", "press_keys",
                   "scroll_ui", "list_windows", "focus_app", "open_application"}),
    ),
    "screen": (
        "See your screen",
        "Look at what's on your screen when you ask about it.",
        frozenset({"see_screen"}),
    ),
    "files": (
        "Work with your files",
        "Find, read, create and edit files and folders. Deleting always asks first.",
        frozenset({"read_file", "write_file", "create_file", "create_folder",
                   "list_directory", "delete_path", "read_document",
                   "read_spreadsheet", "edit_spreadsheet", "search_files",
                   "write_document_section", "mission"}),
    ),
    "commands": (
        "Run commands",
        "Run programs and terminal commands.",
        frozenset({"run_command"}),
    ),
    "coding": (
        "Work with code",
        "Read and edit code projects, run and watch dev servers, and use your code "
        "editor. On automatically while your editor is connected to Mike.",
        frozenset({"read_lines", "edit_file", "multi_edit", "project_overview",
                   "project_tree", "search_code", "check_syntax",
                   "ide_context", "ide_open_file", "ide_apply_edit",
                   "run_background", "list_processes", "process_output",
                   "kill_process", "check_port", "check_url"}),
    ),
    "web": (
        "Use the web",
        "Search the web and open websites. Searches are sent to the search engine.",
        frozenset({"search_web", "open_url", "open_browser"}),
    ),
    "email": (
        "Send email",
        "Send email from your connected Gmail. Always asks before sending.",
        frozenset({"send_email"}),
    ),
    "memory": (
        "Remember things",
        "Keep facts you ask Mike to remember, across chats.",
        frozenset({"remember", "recall_memory", "forget_memory"}),
    ),
}

_PREF = "abilities_off"
_PREF_ON = "abilities_on"
#: Off until the user turns them on (or, for coding, connects their editor).
DEFAULT_OFF = frozenset({"coding"})


def _pref_set(name: str) -> set[str]:
    try:
        from config import preferences
        raw = str(preferences.get(name, "") or "")
    except Exception:
        raw = ""
    return {k for k in (p.strip() for p in raw.split(",")) if k in ABILITIES}


def _editor_connected() -> bool:
    try:
        from ide import manager
        return manager.is_connected()
    except Exception:
        return False


def disabled() -> set[str]:
    """The abilities that are off right now."""
    off = _pref_set(_PREF) | (DEFAULT_OFF - _pref_set(_PREF_ON))
    if "coding" in off and "coding" not in _pref_set(_PREF) and _editor_connected():
        off.discard("coding")
    return off


def is_enabled(ability: str) -> bool:
    return ability not in disabled()


def set_enabled(ability: str, on: bool) -> None:
    from config import preferences
    off, turned_on = _pref_set(_PREF), _pref_set(_PREF_ON)
    if on:
        off.discard(ability)
        if ability in DEFAULT_OFF:
            turned_on.add(ability)
    else:
        off.add(ability)
        turned_on.discard(ability)
    preferences.set_value(_PREF, ",".join(sorted(off)))
    preferences.set_value(_PREF_ON, ",".join(sorted(turned_on)))


def ability_of(tool_name: str) -> str | None:
    for key, (_t, _d, tools) in ABILITIES.items():
        if tool_name in tools:
            return key
    return None


def blocked(tool_name: str) -> str | None:
    """If this tool is turned off, a sentence saying so; otherwise None."""
    key = ability_of(tool_name)
    if key is None or key not in disabled():
        return None
    title = ABILITIES[key][0]
    return (f"\"{title}\" is off in Settings → Permissions, so this can't be "
            f"done. Nothing was run. Tell them, and that they can turn it on in "
            f"Settings if they want this.")


def allowed_tools(tools: list[dict]) -> list[dict]:
    """The tool schemas the model may be offered right now."""
    off = disabled()
    if not off:
        return tools
    hidden = set().union(*(ABILITIES[k][2] for k in off))
    return [t for t in tools if t.get("function", {}).get("name") not in hidden]
