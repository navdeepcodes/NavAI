"""The prompt prefix has to stay stable, because latency depends on it.

Ollama reuses its KV cache only for a request that *strictly extends* the
previous one. Mike's prefix is expensive — the instructions plus 44 tool
schemas come to roughly 7,500 tokens — so anything that changes earlier in the
sequence throws all of it away and the whole prompt is re-evaluated before the
model starts answering.

Measured on this machine across a growing conversation:

    volatile facts in the system message   3.5s, 3.9s, 3.8s, 3.8s per turn
    recorded into history as they happen   3.8s first turn, then 0.83s

About three seconds a turn, every turn. These tests pin the two properties
that buy it: the system message never varies with volatile state, and history
only ever grows at the end.

They are cheap structural checks on purpose — the timing itself belongs to a
benchmark, but the invariant that *causes* the timing belongs here, where a
well-meaning refactor will trip over it.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import pytest


@pytest.fixture(scope="module")
def runtime():
    from brain.core_runtime import CoreRuntime

    return CoreRuntime()


def test_the_system_message_does_not_move_with_volatile_state(runtime):
    """Frontmost app, situation summary and recent activity all change
    constantly. None of them may reach the system message."""
    core = runtime._core

    core.situation_summary = "The user is working on Project Apollo."
    core.add_tool_result("created folder Apollo")
    runtime._record_user_turn("Rename it to Nova.")
    first = runtime._build_messages()[0]["content"]

    core.situation_summary = "The user switched to Project Zeus entirely."
    core.add_tool_result("opened Safari")
    core.set_vision("A browser window showing a spreadsheet.")
    runtime._record_user_turn("Actually, open the other one.")
    second = runtime._build_messages()[0]["content"]

    assert first == second, (
        "the system message changed with volatile state — every turn will now "
        "re-evaluate the whole ~7,500-token prefix"
    )


def test_a_turn_only_ever_appends(runtime):
    """Each request must strictly extend the last, or the cache is discarded.

    Anything that rewrites or reorders an earlier message breaks this, which
    is exactly what injecting a freshly-built context block used to do.
    """
    core = runtime._core
    core.history.clear()

    runtime._record_user_turn("First thing.")
    before = list(runtime._build_messages())

    core.history.append({"role": "assistant", "content": "Sure."})
    core.situation_summary = "Something entirely different now."
    runtime._record_user_turn("Second thing.")
    after = list(runtime._build_messages())

    assert len(after) > len(before)
    for index, message in enumerate(before):
        assert after[index] == message, (
            f"message {index} changed between turns ({message.get('role')}); "
            "the request no longer extends the previous one"
        )


def test_the_context_snapshot_is_recorded_next_to_its_turn(runtime):
    """The volatile facts still have to reach the model — moving them out of
    the system message must not mean losing them."""
    core = runtime._core
    core.history.clear()

    core.situation_summary = "The user is working on Project Apollo."
    core.add_tool_result("created folder Apollo")
    runtime._record_user_turn("Rename it to Nova.")

    roles = [m["role"] for m in core.history]
    assert roles[-1] == "user", "the user's turn must come last"
    assert "system" in roles[:-1], "the context snapshot was not recorded"

    snapshot = core.history[-2]["content"]
    assert "Apollo" in snapshot, "the situation never reached the model"
    assert "created folder Apollo" in snapshot, "recent activity was lost"


def test_context_snapshots_are_not_summarised_as_conversation(runtime):
    """The snapshots are notes to the model, not things anyone said. Feeding
    them to the summariser produces a summary of Mike's own bookkeeping."""
    core = runtime._core
    core.history.clear()
    core.situation_summary = "Working on Apollo."
    runtime._record_user_turn("Hello there.")

    transcript = "\n".join(
        f"{t.get('role')}: {t.get('content')}"
        for t in core.history
        if t.get("content") and t.get("role") != "system"
    )
    assert "Hello there." in transcript
    assert "Working on Apollo." not in transcript


if __name__ == "__main__":
    from brain.core_runtime import CoreRuntime

    rt = CoreRuntime()
    test_the_system_message_does_not_move_with_volatile_state(rt)
    test_a_turn_only_ever_appends(rt)
    test_the_context_snapshot_is_recorded_next_to_its_turn(rt)
    test_context_snapshots_are_not_summarised_as_conversation(rt)
    print("\nAll prompt-prefix stability tests passed.")
