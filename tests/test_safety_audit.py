"""Adversarial safety audit: can the confirmation boundary be bypassed?

The gate is only worth what its weakest path is worth. If two tools do the
same thing and only one is gated, the gate is decoration -- a model that wants
to avoid the prompt just picks the other tool, and it need not be doing so
deliberately for the user's file to be gone.

That was not hypothetical. write_file was gated; create_file wrote arbitrary
content to an arbitrary path with no confirmation, and silently overwrote
whatever was already there.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _runtime():
    from brain.core_runtime import CoreRuntime
    return CoreRuntime()


# ══ no ungated path to a gated outcome ═════════════════════

def test_creating_a_file_cannot_silently_overwrite_one():
    """The bypass that existed. create_file replaced an existing file's
    contents with no prompt, while write_file -- identical in effect --
    required one."""
    runtime = _runtime()
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "user_data.txt")
    with open(path, "w") as handle:
        handle.write("ORIGINAL")

    result = runtime._execute_tool(
        "create_file", {"path": path, "content": "REPLACED"})

    with open(path) as handle:
        assert handle.read() == "ORIGINAL", "an ungated tool destroyed user data"
    assert "already exists" in str(result.get("result", result.get("error", "")))
    print("PASS: create_file cannot overwrite without the gate")


def test_creating_a_genuinely_new_file_stays_frictionless():
    """Gating every file creation would make ordinary work impossible, and a
    prompt that fires constantly is one the user stops reading."""
    from brain.core_tools import needs_confirmation

    assert not needs_confirmation("create_file", {})
    runtime = _runtime()
    path = os.path.join(tempfile.mkdtemp(), "new.txt")
    result = runtime._execute_tool("create_file", {"path": path, "content": "hi"})
    assert result["status"] == "success"
    assert os.path.exists(path)
    print("PASS: creating a new file needs no confirmation")


def test_every_destructive_filesystem_tool_is_gated():
    from brain.core_tools import needs_confirmation

    for name in ("write_file", "delete_path", "edit_file", "multi_edit",
                 "ide_apply_edit"):
        assert needs_confirmation(name, {}), f"{name} destroys or replaces content"
    print("PASS: destructive filesystem tools are gated")


def test_every_execution_and_external_tool_is_gated():
    from brain.core_tools import needs_confirmation

    for name in ("run_command", "run_background", "kill_process", "send_email"):
        assert needs_confirmation(name, {}), f"{name} executes or leaves the machine"
    print("PASS: execution and external tools are gated")


def test_observation_is_never_gated():
    """A gate on reading would train the user to click through prompts, which
    costs more safety than it buys."""
    from brain.core_tools import needs_confirmation

    for name in ("read_file", "read_lines", "list_directory", "search_code",
                 "search_files", "see_ui", "see_screen", "list_windows",
                 "list_processes", "check_url", "check_port", "check_syntax",
                 "project_tree", "project_overview", "recall_memory"):
        assert not needs_confirmation(name, {}), f"{name} only observes"
    print("PASS: observation is ungated")


def test_the_gate_cannot_be_skipped_by_argument_shape():
    """Confirmation is decided by the action, not by how the call is phrased."""
    from brain.core_tools import needs_confirmation

    for args in ({}, {"path": "/tmp/x"}, {"path": "/tmp/x", "content": ""},
                 {"unexpected": True}, {"path": None}):
        assert needs_confirmation("write_file", args), (
            f"write_file escaped the gate with args={args}"
        )
    print("PASS: the gate does not depend on argument shape")


def test_a_denied_action_changes_nothing_on_disk():
    """The refusal has to happen before execution, not be reported after it."""
    import inspect

    from brain import core_runtime

    source = inspect.getsource(core_runtime)
    gate = source.index("if needs_confirmation(name, args):")
    denial = source.index("User denied this action.", gate)
    execute = source.index("self._execute_tool(", gate)
    assert denial < execute, "a refusal must precede execution"
    print("PASS: denial short-circuits before the action runs")


def test_confirmation_text_describes_the_real_consequence():
    """"Allow write_file?" tells the user nothing they can judge."""
    from brain.core_tools import describe_action

    assert "/tmp/report.txt" in describe_action("write_file", {"path": "/tmp/report.txt"})
    assert "rm -rf" in describe_action("run_command", {"command": "rm -rf /tmp/x"})

    detail = describe_action("send_email", {
        "to": "someone@example.com", "subject": "Q3", "body": "hi", "attachments": []})
    assert "someone@example.com" in detail and "cannot be recalled" in detail
    print("PASS: confirmations name the actual consequence")


def test_raw_coordinate_clicks_stay_gated():
    """A reference is checked against a real element; a coordinate is not."""
    from brain.core_tools import needs_confirmation

    assert needs_confirmation("click_element", {"x": 100, "y": 200})
    assert not needs_confirmation("click_element", {"ref": "el3"})
    print("PASS: unverifiable coordinate clicks require confirmation")


def test_memory_deletion_is_scoped_and_reported():
    """Forgetting is destructive to user data, so it must report exactly what
    it removed rather than claiming success vaguely."""
    import tempfile as tf

    os.environ["MIKE_DATA_DIR"] = tf.mkdtemp(prefix="forget-")
    from importlib import reload

    from brain import memory_store
    reload(memory_store)

    memory_store.remember("a fact worth keeping", "fact")
    memory_store.remember("a fact to remove", "fact")
    before = len(memory_store.all_memories())

    result = memory_store.forget(query="remove")
    after = memory_store.all_memories()

    assert before - len(after) == 1, "forget removed the wrong number of memories"
    assert "1" in result["result"], f"it must say what it removed: {result['result']!r}"
    assert any("keeping" in m["content"] for m in after), "it deleted the wrong one"
    print("PASS: forgetting removes exactly what was asked for and says so")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nAll safety audit tests passed.")
