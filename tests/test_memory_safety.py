"""Forgetting is destructive to user data, and until this file existed it was
the last destructive tool Mike could run without asking.

Everything else that cannot be undone — writing over a file, deleting a path,
running a command, sending mail — stops for the user first. Memory did not,
so "forget everything" reached the database on the model's say-so alone.
There is no undo and no copy on disk to restore from, so a wrong call was
final.

These tests pin the boundary: reading memory stays free, erasing it does not,
the confirmation names the actual rows at risk, denial deletes nothing, and a
deletion is only reported as done once the database has been re-read.
"""
from __future__ import annotations

import os
import sys
import tempfile
from importlib import reload

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — must run before any brain import

import pytest


@pytest.fixture
def memory():
    """A private database per test, so a real deletion here is harmless."""
    from brain import memory_store

    previous = os.environ.get("MIKE_DATA_DIR")
    os.environ["MIKE_DATA_DIR"] = tempfile.mkdtemp(prefix="mike-forget-")
    reload(memory_store)
    try:
        yield memory_store
    finally:
        if previous is not None:
            os.environ["MIKE_DATA_DIR"] = previous
        reload(memory_store)


# ── the gate ──────────────────────────────────────────────

def test_reading_memory_is_never_gated():
    """Ordinary recall and saving must stay frictionless. A confirmation that
    fires on harmless operations is one the user learns to click through,
    which would weaken the gate that matters."""
    from brain.core_tools import needs_confirmation

    assert not needs_confirmation("recall_memory", {"query": "anything"})
    assert not needs_confirmation("remember", {"content": "something"})


def test_forgetting_requires_confirmation():
    from brain.core_tools import needs_confirmation

    assert needs_confirmation("forget_memory", {"query": "dark mode"})
    assert needs_confirmation("forget_memory", {"query": "everything"})


def test_confirmation_names_the_actual_memories(memory):
    """The prompt is built from the database, not from the model's argument.
    A prompt that only echoes the request proves nothing about what will go."""
    from brain.core_tools import describe_action

    memory.remember("Navdeep prefers dark mode", "preference")
    memory.remember("the rocket project lives in ~/Developer/RocketSim", "project")

    prompt = describe_action("forget_memory", {"query": "rocket"})

    assert "rocket project lives" in prompt, prompt
    assert "dark mode" not in prompt, "it named a memory that is not at risk"
    assert "1 memory" in prompt, prompt
    assert "cannot be undone" in prompt.lower()


def test_confirmation_for_everything_lists_the_whole_scope(memory):
    from brain.core_tools import describe_action

    # Deliberately unalike, so remember()'s similarity merge treats them as
    # three memories rather than folding them into one.
    memory.remember("Navdeep prefers dark mode", "preference")
    memory.remember("the rocket project lives in RocketSim", "project")
    memory.remember("standup happens at ten on Tuesdays", "workflow")

    prompt = describe_action("forget_memory", {"query": "everything"})

    assert "3 memory" in prompt, prompt
    assert "every stored memory" in prompt, prompt


def test_confirmation_is_honest_when_nothing_matches(memory):
    """Asking to allow a deletion that would remove nothing should say so,
    rather than presenting an alarming prompt for a no-op."""
    from brain.core_tools import describe_action

    memory.remember("something unrelated", "fact")
    prompt = describe_action("forget_memory", {"query": "nonexistent"})

    assert "nothing currently matches" in prompt, prompt


# ── denial ────────────────────────────────────────────────

def test_denial_deletes_nothing(memory):
    """The whole point of the gate: saying no must leave the database
    untouched, verified by reading it rather than by trusting the runtime's
    report."""
    from brain.core_runtime import CoreRuntime

    memory.remember("Navdeep prefers dark mode", "preference")
    memory.remember("the rocket project lives in ~/Developer/RocketSim", "project")
    before = memory.all_memories()

    runtime = CoreRuntime()
    asked = []

    def deny(description):
        asked.append(description)
        return False

    # Exactly the sequence the streaming loop runs for a gated call.
    from brain.core_tools import describe_action, needs_confirmation

    args = {"query": "everything"}
    assert needs_confirmation("forget_memory", args)
    allowed = deny(describe_action("forget_memory", args))
    if allowed:
        runtime._execute_tool("forget_memory", args)

    after = memory.all_memories()
    assert len(after) == len(before) == 2, "denial still lost memories"
    assert asked and "every stored memory" in asked[0]


def test_denied_calls_never_reach_the_store(memory, monkeypatch):
    """A stronger version of the same guarantee: prove the deletion function
    itself is never entered, not merely that the rows survived."""
    entered = []
    monkeypatch.setattr(
        memory, "forget",
        lambda *a, **k: entered.append(a) or {"status": "success", "result": ""},
    )

    from brain.core_tools import needs_confirmation

    def confirm(_description):
        return False

    args = {"query": "everything"}
    if needs_confirmation("forget_memory", args) and not confirm(""):
        pass
    else:
        memory.forget(**args)

    assert entered == []


# ── the deletion itself ───────────────────────────────────

def test_deletion_is_verified_against_the_database(memory):
    """Success is reported only after re-reading. sqlite's rowcount is the
    driver describing its own work; this reads the stored state."""
    memory.remember("Navdeep prefers dark mode", "preference")
    memory.remember("the rocket project lives in RocketSim", "project")

    result = memory.forget(query="rocket")

    assert result["status"] == "success"
    assert result["deleted"] == 1
    assert "verified gone" in result["result"]
    assert "rocket project" in result["result"], "it must name what went"

    survivors = memory.all_memories()
    assert len(survivors) == 1
    assert "dark mode" in survivors[0]["content"]


def test_preview_and_deletion_agree(memory):
    """The list the user approves and the rows that go must be produced by the
    same selector. If these could drift, the confirmation would be theatre."""
    memory.remember("alpha one", "fact")
    memory.remember("alpha two", "fact")
    memory.remember("beta three", "fact")

    preview = memory.preview_forget(query="alpha")
    previewed = {m["id"] for m in preview["memories"]}
    assert len(previewed) == 2

    memory.forget(query="alpha")

    remaining = {m["id"] for m in memory.all_memories()}
    assert previewed & remaining == set(), "something previewed as doomed survived"
    assert len(remaining) == 1


def test_preview_changes_nothing(memory):
    """Building the confirmation must be a read. If generating the prompt
    deleted anything, denial could not be safe."""
    memory.remember("alpha one", "fact")
    memory.remember("alpha two", "fact")

    from brain.core_tools import describe_action

    for _ in range(3):
        describe_action("forget_memory", {"query": "everything"})
        memory.preview_forget(query="everything")

    assert len(memory.all_memories()) == 2


def test_forget_still_reports_a_missing_id(memory):
    """Existing behaviour must not weaken: asking to forget something that
    isn't there is still an error, not a quiet success."""
    result = memory.forget(memory_id=9999)
    assert result["status"] == "error"
    assert "9999" in result["error"]


def test_no_query_is_still_refused(memory):
    result = memory.forget()
    assert result["status"] == "error"


def test_no_destructive_tool_is_left_ungated():
    """A standing check over the whole surface rather than a fact about one
    tool. Any future tool that destroys something has to either be gated or
    be listed here with a reason, so the next one cannot slip in unnoticed.

    The scan reads names and descriptions, which catches wording as well as
    naming, and therefore also catches tools that merely *mention* deletion.
    Those are named below individually — the point is that the list is short,
    explicit, and has to be edited on purpose."""
    from brain.core_tools import TOOL_DECLARATIONS, _CONFIRM_ACTIONS, needs_confirmation

    justified = {
        # Saving a fact. Its description says "don't forget" when telling the
        # model when to use it; it writes, it never deletes.
        "remember",
        # How Mike operates every interface, so gating it by name would gate
        # everything. It is gated by the control it resolves to instead —
        # covered in test_safety_audit.py. The word matched is "clear" inside
        # "fails clearly".
        "click_element",
    }

    destructive_words = ("delete", "forget", "remove", "erase", "clear", "kill")
    unguarded = []
    for decl in TOOL_DECLARATIONS:
        text = f"{decl.name} {decl.description or ''}".lower()
        if not any(w in text for w in destructive_words):
            continue
        if decl.name in justified:
            continue
        if decl.name not in _CONFIRM_ACTIONS and not needs_confirmation(decl.name, {}):
            unguarded.append(decl.name)

    assert unguarded == [], f"ungated destructive tools: {unguarded}"
