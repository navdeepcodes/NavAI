"""What survives in the conversation window, and why it matters.

These pin the fix for a real-world failure: Mike stopped understanding
ordinary references — "change its name", "send it to Sarah instead", "close
it" — after he had done a few tasks. It read as the model being weak at
coreference. It was not. The conversation had been evicted from the window by
Mike's own tool traffic.

Every agent step appends an assistant message plus one `tool` message per
call, so an ordinary task adds dozens of entries. With a flat "keep the last N
messages" rule, the loud thing wins: measured before the fix, two twelve-step
tasks left a 40-message window holding 20 assistant, 18 tool and *two* user
messages, with the name the user had chosen already gone.

The rule these tests hold the code to is that the conversation is the last
thing given up, never the first — and that the turn Mike is currently working
through keeps its own working state regardless.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

from brain.mike_core import MAX_HISTORY, MikeCore, _segment_history


def _core() -> MikeCore:
    return MikeCore(host="http://127.0.0.1:11434", summary_model="qwen3.5:9b")


def _run_task(core: MikeCore, label: str, steps: int) -> None:
    """One ordinary multi-step task, appended exactly the way the runtime does."""
    core.history.append({"role": "user", "content": label})
    for i in range(steps):
        call_id = f"{label[:4]}{i}"
        core.history.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id,
                            "function": {"name": "create_file", "arguments": {}}}],
        })
        core.history.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps({"status": "ok", "result": "x" * 80}),
        })
    core.history.append({"role": "assistant", "content": "Done."})
    core.trim_history()


def test_what_the_user_said_survives_a_pile_of_tool_work():
    """The reported bug, reproduced as a test: name a thing, do several tasks,
    then refer back to it. The name has to still be there."""
    core = _core()
    core.history.append({"role": "user", "content": "Let's call the project Apollo."})
    core.history.append({"role": "assistant", "content": "Got it — Apollo it is."})
    core.trim_history()

    for i in range(10):
        _run_task(core, f"Task number {i}.", 12)

    core.history.append({"role": "user", "content": "Change its name to Nova."})
    core.trim_history()

    assert any("Apollo" in (m.get("content") or "") for m in core.history), (
        "the name the user chose was evicted by tool traffic — 'its' now "
        "refers to nothing"
    )
    users = [m for m in core.history if m.get("role") == "user"]
    assert len(users) >= 8, f"only {len(users)} user turns survived 120 tool calls"


def test_the_running_turn_keeps_its_own_working_state():
    """Protecting the conversation must not cost Mike the steps he has already
    taken in the task he is in the middle of — that would make him repeat
    work."""
    core = _core()
    core.history.append({"role": "user", "content": "Let's call the project Apollo."})
    for i in range(6):
        _run_task(core, f"Earlier task {i}.", 12)

    core.history.append({"role": "user", "content": "Now do the big one."})
    for i in range(20):
        core.history.append({
            "role": "assistant", "content": "",
            "tool_calls": [{"id": f"big{i}",
                            "function": {"name": "f", "arguments": {}}}],
        })
        core.history.append({
            "role": "tool", "tool_call_id": f"big{i}",
            "content": json.dumps({"result": f"step {i}"}),
        })
        core.trim_history()

    live = [m for m in core.history
            if m.get("role") == "tool" and "step " in (m.get("content") or "")]
    assert len(live) == 20, (
        f"the current turn lost {20 - len(live)} of its own steps; Mike would "
        "redo work he has already done"
    )


def test_history_stays_within_its_ceiling():
    core = _core()
    for i in range(12):
        _run_task(core, f"Task {i}.", 12)
    assert len(core.history) <= MAX_HISTORY


def test_a_tool_result_is_never_separated_from_its_call():
    """An orphaned tool result is uninterpretable, and some providers reject
    it outright. Trimming moves whole exchanges or nothing."""
    core = _core()
    for i in range(12):
        _run_task(core, f"Task {i}.", 12)

    seen_call = False
    for message in core.history:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            seen_call = True
        elif message.get("role") == "tool":
            assert seen_call, "a tool result survived without the call that caused it"
        else:
            seen_call = False


def test_segmentation_groups_a_call_with_its_results():
    history = [
        {"role": "user", "content": "do it"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}, {"id": "b"}]},
        {"role": "tool", "tool_call_id": "a", "content": "{}"},
        {"role": "tool", "tool_call_id": "b", "content": "{}"},
        {"role": "assistant", "content": "done"},
    ]
    segments = _segment_history(history)
    kinds = [kind for kind, _ in segments]
    assert kinds == ["talk", "tool", "talk"]
    assert len(segments[1][1]) == 3, "the call and both results must move together"


if __name__ == "__main__":
    test_what_the_user_said_survives_a_pile_of_tool_work()
    test_the_running_turn_keeps_its_own_working_state()
    test_history_stays_within_its_ceiling()
    test_a_tool_result_is_never_separated_from_its_call()
    test_segmentation_groups_a_call_with_its_results()
    print("\nAll conversational-context tests passed.")
