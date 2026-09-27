"""A smaller prompt and fewer wasted calls, with every action still verified."""
import pytest


def test_a_shortcut_written_as_one_key_is_pressed_as_a_shortcut():
    from computer.session import ComputerSession
    from computer.base import ActionResult

    class Keys:
        pressed = []
        def available(self): return True, "ok"
        def frontmost_app(self): return "Notepad"
        def press_keys(self, key, modifiers=None):
            self.pressed.append((key, list(modifiers or [])))
            return ActionResult(True, "pressed")

    session = ComputerSession()
    session._controller = Keys()
    session.press_keys("ctrl+a")
    session.press_keys("Ctrl+Shift+S")
    session.press_keys("+")
    assert Keys.pressed == [("a", ["ctrl"]), ("S", ["Ctrl", "Shift"]), ("+", [])]


@pytest.fixture
def prefs(monkeypatch):
    store = {}
    from config import preferences
    monkeypatch.setattr(preferences, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(preferences, "set_value", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr("brain.permissions._editor_connected", lambda: False)
    return store


def test_coding_tools_are_off_until_turned_on(prefs):
    from brain import permissions
    from brain.core_tools import OLLAMA_TOOLS
    offered = {t["function"]["name"] for t in permissions.allowed_tools(OLLAMA_TOOLS)}
    assert "edit_file" not in offered and "read_file" in offered and "open_application" in offered
    assert permissions.blocked("edit_file")
    permissions.set_enabled("coding", True)
    assert "edit_file" in {t["function"]["name"] for t in permissions.allowed_tools(OLLAMA_TOOLS)}
    assert permissions.blocked("edit_file") is None
    permissions.set_enabled("coding", False)
    assert permissions.blocked("edit_file")


def test_a_connected_editor_turns_coding_on_unless_the_user_turned_it_off(prefs, monkeypatch):
    from brain import permissions
    monkeypatch.setattr("brain.permissions._editor_connected", lambda: True)
    assert permissions.is_enabled("coding")
    permissions.set_enabled("coding", False)
    assert not permissions.is_enabled("coding")


def test_code_instructions_come_with_the_coding_tools(prefs):
    from brain import permissions
    from brain.core_runtime import system_prompt
    assert "check_syntax" not in system_prompt() and "project_overview" not in system_prompt()
    permissions.set_enabled("coding", True)
    assert "check_syntax" in system_prompt()


def test_every_tool_still_belongs_to_exactly_one_permission():
    from brain import permissions
    from brain.core_tools import OLLAMA_TOOLS
    groups = [tools for _t, _d, tools in permissions.ABILITIES.values()]
    for t in OLLAMA_TOOLS:
        name = t["function"]["name"]
        if name == "calculate":
            continue
        assert sum(name in g for g in groups) == 1, name
