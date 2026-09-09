"""Starting and fully stopping a process tree, cross-platform.

`tools/terminal/actions.py` starts background commands (a dev server, a
watcher) with `shell=True` and needs to stop the whole tree later — the
actual server a shell spawned, not just the shell that spawned it. On POSIX
that used `start_new_session=True` plus `os.killpg(os.getpgid(pid), SIGTERM)`,
which is exactly right on macOS and Linux and does not exist on Windows:
`os.killpg`/`os.getpgid` raise `AttributeError` there. The original code
caught that under a bare `except Exception` and fell through to
`process.terminate()`, which stops only the shell — not the real process it
spawned. That is a real leak, not a hypothetical one: it would have shipped
silently, because nothing raised.

Windows has its own equivalent of a process group — `CREATE_NEW_PROCESS_GROUP`
— and its own two-stage shutdown: `CTRL_BREAK_EVENT` as the closest thing it
has to a polite SIGTERM (not every console process honours it, the same way
not every POSIX process honours SIGTERM), and `taskkill /T /F` — shipped on
every Windows install, no extra dependency — as the forceful tree-kill that
actually reaches children a shell spawned. Both real OS-level mechanisms, not
a Job Object wrapper pretending to be one and not a plain `process.kill()`
that only reaches the shell.
"""
from __future__ import annotations

import os
import platform
import signal
import subprocess


def spawn_detached(command: str, *, cwd: str | None = None,
                    **popen_kwargs) -> subprocess.Popen:
    """Start a shell command in its own process group/session.

    Grouping it is what makes `terminate_tree` able to stop the whole tree
    later rather than only the immediate shell process. Only a process
    started this way can be passed to `terminate_tree` and have that promise
    kept — a process started any other way has no group to terminate as a
    unit, and only the single process can be reached.
    """
    kwargs = dict(popen_kwargs)
    if platform.system() == "Windows":
        kwargs["creationflags"] = (
            kwargs.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, shell=True, cwd=cwd, **kwargs)


def terminate_tree(process: subprocess.Popen, *, timeout: float = 5.0) -> None:
    """Stop `process` and everything it spawned.

    Must be called on a process started by `spawn_detached` — passed anything
    else, only the single process can be reached, on either platform.
    Idempotent: safe to call on a process that has already exited.
    """
    if platform.system() == "Windows":
        _terminate_tree_windows(process, timeout)
    else:
        _terminate_tree_posix(process, timeout)


def _terminate_tree_posix(process: subprocess.Popen, timeout: float) -> None:
    if process.poll() is not None:
        return
    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pass


def _terminate_tree_windows(process: subprocess.Popen, timeout: float) -> None:
    if process.poll() is not None:
        return
    # The polite attempt first. CTRL_BREAK_EVENT reaches every process in the
    # group CREATE_NEW_PROCESS_GROUP created, the nearest Windows equivalent
    # to SIGTERM reaching a POSIX process group — but, like SIGTERM, nothing
    # obliges a process to act on it.
    try:
        process.send_signal(signal.CTRL_BREAK_EVENT)
        process.wait(timeout=timeout)
        return
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    # taskkill /T /F is the forceful, whole-tree kill every Windows install
    # ships with. It reaches children a shell spawned the same way killing a
    # POSIX process group does, with no extra dependency (no pywin32, no Job
    # Object plumbing) — a real OS mechanism, not a partial stand-in for one.
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
        capture_output=True,
    )
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
