"""hostplatform.processes: real process-tree termination, on this OS.

This is the adapter-conformance layer Phase 16 asks for: one test file that
exercises the actual contract (spawn a tree, terminate it, prove every member
is gone) against whichever platform this happens to run on. It is not a mock
of process termination — every process here is real, and "gone" is verified
by asking the OS, not by trusting a return value.

The bug this guards against was real and silent: `os.killpg`/`os.getpgid`
raise `AttributeError` on Windows, and the code that used them caught that
under a bare `except Exception` and fell through to `process.terminate()` —
which stops only the immediate shell, leaking every child it spawned. Nothing
would have raised. It would have shipped.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

from hostplatform import processes


def _pid_alive(pid: int) -> bool:
    if platform.system() == "Windows":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, text=True,
        ).stdout
        return str(pid) in out
    return subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode == 0


def _child_pids(parent_pid: int) -> list[int]:
    """Every process that reports `parent_pid` as its parent, right now."""
    if platform.system() == "Windows":
        out = subprocess.run(
            ["wmic", "process", "where", f"(ParentProcessId={parent_pid})",
             "get", "ProcessId"],
            capture_output=True, text=True,
        ).stdout
        return [int(line.strip()) for line in out.splitlines()[1:] if line.strip().isdigit()]
    out = subprocess.run(["pgrep", "-P", str(parent_pid)], capture_output=True, text=True).stdout
    return [int(p) for p in out.split() if p.strip()]


# A shell command that spawns a real, independently-visible child process —
# not just sleeps itself — so the test actually exercises "the whole tree
# dies", not only "the shell dies".
if platform.system() == "Windows":
    _TREE_COMMAND = 'start /B cmd /C "ping -n 30 127.0.0.1 >NUL"'
else:
    _TREE_COMMAND = "sleep 30 & wait"


def test_spawn_detached_starts_a_real_group_and_terminate_tree_ends_it():
    process = processes.spawn_detached(
        _TREE_COMMAND,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.6)
        assert _pid_alive(process.pid), "the spawned process never started"

        started = time.perf_counter()
        processes.terminate_tree(process, timeout=5)
        elapsed = time.perf_counter() - started

        assert elapsed < 6, f"terminate_tree took {elapsed:.1f}s"
        time.sleep(0.3)
        assert not _pid_alive(process.pid), "the process survived terminate_tree"
    finally:
        if process.poll() is None:
            process.kill()
    print("PASS: spawn_detached + terminate_tree ends a real process")


def test_terminate_tree_is_safe_on_an_already_finished_process():
    process = processes.spawn_detached(
        "exit 0" if platform.system() != "Windows" else "cmd /C exit 0",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    process.wait(timeout=5)
    processes.terminate_tree(process, timeout=2)   # must not raise
    processes.terminate_tree(process, timeout=2)   # idempotent
    print("PASS: terminate_tree on an already-finished process is a no-op")


def test_terminate_tree_kills_children_the_shell_spawned():
    """The actual regression: a leaked child that outlives its shell.

    Terminating only the immediate process (the old fallback path this
    replaces) would leave this child running; terminate_tree must not.
    """
    process = processes.spawn_detached(
        _TREE_COMMAND,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.6)
        children_before = _child_pids(process.pid)

        processes.terminate_tree(process, timeout=5)
        time.sleep(0.3)

        for child_pid in children_before:
            assert not _pid_alive(child_pid), (
                f"child pid {child_pid} survived terminate_tree — this is "
                "exactly the leak a bare process.terminate() produces"
            )
    finally:
        if process.poll() is None:
            process.kill()
    print("PASS: terminate_tree reaches children the shell spawned")


if __name__ == "__main__":
    test_spawn_detached_starts_a_real_group_and_terminate_tree_ends_it()
    test_terminate_tree_is_safe_on_an_already_finished_process()
    test_terminate_tree_kills_children_the_shell_spawned()
    print("\nAll hostplatform.processes tests passed.")
