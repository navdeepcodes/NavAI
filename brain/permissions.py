"""What Mike is allowed to do — decided by the person, enforced by the runtime.

Each ability groups the tools that make it possible. Turning one off in
Settings → Permissions does two things, so it can't be talked around:

  1. the tools disappear from what the model is offered at all, so it never
     plans with them, and
  2. a call to one anyway (a stale plan, a confused model) is refused before
     anything runs, with a message saying the user turned it off.

Everything is on by default — this narrows what Mike does; it never widens
what he could do without asking. Confirmation for destructive actions stays
exactly as it is, whatever is switched on here.
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
                   "read_lines", "edit_file", "multi_edit", "project_overview",
                   "project_tree", "search_code", "check_syntax",
                   "ide_context", "ide_open_file", "ide_apply_edit"}),
    ),
    "commands": (
        "Run commands",
        "Run programs and terminal commands, and manage what they start.",
        frozenset({"run_command", "run_background", "list_processes",
                   "process_output", "kill_process", "check_port"}),
    ),
    "web": (
        "Use the web",
        "Search the web and open websites. Searches are sent to the search engine.",
        frozenset({"search_web", "open_url", "open_browser", "check_url"}),
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


def disabled() -> set[str]:
    """The abilities the user has turned off."""
    try:
        from config import preferences
        raw = str(preferences.get(_PREF, "") or "")
    except Exception:
        raw = ""
    return {k for k in (p.strip() for p in raw.split(",")) if k in ABILITIES}


def is_enabled(ability: str) -> bool:
    return ability not in disabled()


def set_enabled(ability: str, on: bool) -> None:
    from config import preferences
    off = disabled()
    (off.discard if on else off.add)(ability)
    preferences.set_value(_PREF, ",".join(sorted(off)))


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
    return (f"The user has turned off \"{title}\" in Settings → Permissions, so "
            f"this can't be done. Nothing was run. Tell them, and that they can "
            f"turn it back on in Settings if they want this.")


def allowed_tools(tools: list[dict]) -> list[dict]:
    """The tool schemas the model may be offered right now."""
    off = disabled()
    if not off:
        return tools
    hidden = set().union(*(ABILITIES[k][2] for k in off))
    return [t for t in tools if t.get("function", {}).get("name") not in hidden]
