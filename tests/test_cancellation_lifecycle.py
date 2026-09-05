"""Cancellation and background-process lifecycle.

Both are places where "it looked like it worked" is easy and wrong: a
cancelled task that leaves half a tool call in the history poisons the next
turn, and a killed server that stays in the process registry makes Mike report
state that no longer exists.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _terminal():
    from tools.terminal import actions
    return actions


# ══ cancellation ═══════════════════════════════════════════

def test_a_cancel_set_before_starting_produces_no_work():
    from brain.core_runtime import CoreRuntime

    cancelled = threading.Event()
    cancelled.set()
    runtime = CoreRuntime()
    events = [k for k, _ in runtime.process_streaming(
        "List every file on this machine", confirm_callback=lambda d: True,
        cancel_event=cancelled)]

    assert "tool_start" not in events, "nothing may run when cancelled up front"
    print("PASS: a pre-set cancel prevents any work")


def test_cancelling_leaves_no_orphaned_tool_message():
    """A tool message with no preceding assistant turn is a malformed history
    that the next request has to carry."""
    from brain.core_runtime import CoreRuntime

    cancelled = threading.Event()
    cancelled.set()
    runtime = CoreRuntime()
    list(runtime.process_streaming("Read a file", confirm_callback=lambda d: True,
                                   cancel_event=cancelled))

    history = runtime._core.history
    orphans = [i for i, m in enumerate(history)
               if m.get("role") == "tool"
               and (i == 0 or history[i - 1].get("role") not in ("assistant", "tool"))]
    assert not orphans, f"orphaned tool messages at {orphans}"
    print("PASS: cancellation leaves a coherent history")


def test_the_runtime_still_works_after_a_cancel():
    from brain.core_runtime import CoreRuntime

    cancelled = threading.Event()
    cancelled.set()
    runtime = CoreRuntime()
    list(runtime.process_streaming("anything", confirm_callback=lambda d: True,
                                   cancel_event=cancelled))

    result = runtime._execute_tool("list_directory", {"path": tempfile.mkdtemp()})
    assert result["status"] == "success", "a cancel must not break the runtime"
    print("PASS: the runtime is usable after a cancellation")


# ══ terminal timeouts ══════════════════════════════════════

def test_a_command_that_hangs_is_stopped_at_its_timeout():
    started = time.time()
    result = _terminal().run("sleep 30", timeout=3)
    elapsed = time.time() - started

    assert result["timed_out"] is True
    assert elapsed < 10, f"timeout was not honoured: {elapsed:.1f}s"
    print(f"PASS: a hanging command is stopped at its timeout ({elapsed:.1f}s)")


def test_a_failing_command_reports_its_exit_code():
    """A non-zero exit is information the model needs, not an exception."""
    result = _terminal().run("exit 7", timeout=10)
    assert result["exit_code"] == 7
    assert result["timed_out"] is False
    print("PASS: a non-zero exit code is reported")


# ══ background processes ═══════════════════════════════════

def test_a_killed_process_actually_dies():
    terminal = _terminal()
    pid = terminal.run_background("sleep 60")["pid"]
    time.sleep(0.6)
    terminal.kill_process(pid)
    time.sleep(0.8)

    alive = subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode == 0
    assert not alive, f"pid {pid} survived kill_process"
    print("PASS: a killed background process is actually gone")


def test_shutdown_kills_everything_and_clears_the_registry():
    """The processes were being killed correctly, but their entries stayed --
    so a listing after teardown described dead servers as session state."""
    terminal = _terminal()
    pids = [terminal.run_background("sleep 60")["pid"] for _ in range(3)]
    time.sleep(0.8)

    terminal.shutdown_all()
    time.sleep(1.0)

    for pid in pids:
        alive = subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode == 0
        assert not alive, f"pid {pid} orphaned after shutdown_all"

    listing = terminal.list_processes()
    assert listing["count"] == 0, f"registry not cleared: {listing['count']} entries"
    print("PASS: shutdown leaves no processes and no stale entries")


def test_listing_processes_describes_them_in_the_result_key():
    """Every other tool reports under 'result', and the activity log reads it.
    Returning only structured data logged a successful listing as 'Done'."""
    terminal = _terminal()
    terminal.shutdown_all()

    empty = terminal.list_processes()
    assert "result" in empty and "No background processes" in empty["result"]

    pid = terminal.run_background("sleep 30")["pid"]
    time.sleep(0.5)
    listed = terminal.list_processes()
    assert "result" in listed
    assert str(pid) in listed["result"]
    assert "running" in listed["result"]

    terminal.shutdown_all()
    print("PASS: process listings describe themselves")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nAll cancellation and lifecycle tests passed.")
