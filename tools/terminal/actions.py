from __future__ import annotations

import itertools
import os
import subprocess
import threading
import time

from hostplatform import processes
from logs.logger import logger

# Commands that finish are expected to finish reasonably quickly. Anything
# that doesn't is either stuck or is really a long-running process, which
# belongs in run_background instead.
DEFAULT_TIMEOUT = 60

# Enough for a real test run or build log to survive; past this the head and
# tail carry the useful parts (what ran, and what failed) far better than an
# arbitrary prefix would.
MAX_STREAM_CHARS = 30_000


def _clip(text: str) -> str:
    """Keeps both ends of a long stream — a build log's failure is usually at
    the end, while what ran is at the start. A plain prefix loses the error."""
    text = text or ""
    if len(text) <= MAX_STREAM_CHARS:
        return text
    head = MAX_STREAM_CHARS // 2
    tail = MAX_STREAM_CHARS - head
    dropped = len(text) - MAX_STREAM_CHARS
    return (
        text[:head]
        + f"\n\n--- {dropped:,} characters omitted from the middle ---\n\n"
        + text[-tail:]
    )


def run(
    command: str,
    cwd: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Execute a shell command and return everything the caller needs to judge
    what happened: exit code, stdout, stderr, where it ran, how long it took.

    Deliberately does NOT raise on a non-zero exit. A failing command is a
    normal, informative outcome — a test suite reporting failures, a build
    surfacing errors, a grep finding nothing. Raising discarded exactly the
    output needed to act on it: before this, `pytest` failing returned the
    string "Command failed." and nothing else, because the failures went to
    stdout and only stderr survived the exception. Non-zero is reported as
    data, not as an error.
    """

    if not command.strip():
        raise ValueError("Command cannot be empty.")

    workdir = cwd or os.getcwd()
    logger.info("Running command: %s (cwd=%s)", command, workdir)

    started = time.monotonic()

    # spawn_detached + terminate_tree, not subprocess.run(timeout=...): a
    # command that spawns a real child (not just itself) leaves that child
    # holding the inherited stdout/stderr pipe open, so subprocess.run's own
    # timeout kills only the shell and then blocks reading output until the
    # child exits on its own — verified directly, "sleep 5" under a 2s
    # timeout still took the full 5s. terminate_tree reaches the whole tree,
    # which is the actual fix, on both platforms — POSIX's plain
    # process.kill() had the identical gap, just never exercised.
    try:
        process = processes.spawn_detached(
            command, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
    except FileNotFoundError as exc:
        return {
            "exit_code": None,
            "timed_out": False,
            "stdout": "",
            "stderr": str(exc),
            "cwd": workdir,
            "command": command,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }

    # Read as it comes, so a command that turns out to be a server can be
    # handed over still running, with what it has printed so far.
    out: list[str] = []
    err: list[str] = []
    merged: list[str] = []
    readers = [threading.Thread(target=_collect, args=(stream, bucket, merged), daemon=True)
               for stream, bucket in ((process.stdout, out), (process.stderr, err))]
    for reader in readers:
        reader.start()

    def finished(**extra) -> dict:
        return {"stdout": _clip("".join(out)), "stderr": _clip("".join(err)), "cwd": workdir,
                "command": command, "duration_ms": round((time.monotonic() - started) * 1000),
                **extra}

    deadline = started + timeout
    while True:
        try:
            process.wait(timeout=max(0.0, min(_SERVER_CHECK_EVERY, deadline - time.monotonic())))
            break
        except subprocess.TimeoutExpired:
            pass
        if time.monotonic() >= deadline:
            processes.terminate_tree(process, timeout=5)
            # The tree is gone, so every pipe writer has exited and the
            # readers finish with whatever was already buffered.
            _join(readers)
            return finished(exit_code=None, timed_out=True, timeout_seconds=timeout)
        # Still going: has it turned out to be a server? Waiting on one to
        # finish held a whole task up for the full minute (measured: a
        # student's site built in 116s, 60 of them this wait).
        if time.monotonic() - started >= _SERVER_CHECK_AFTER:
            ports = processes.listening_ports(process.pid)
            if ports:
                _adopt(process, command, workdir, merged)
                return finished(exit_code=None, timed_out=False, still_running=True,
                                pid=process.pid, listening_on=ports)

    _join(readers)
    return finished(exit_code=process.returncode, timed_out=False)


#: When a command is still going after this long, Mike starts checking whether
#: it's really a server -- a process listening on a port -- and how often.
_SERVER_CHECK_AFTER = 3.0
_SERVER_CHECK_EVERY = 1.5


def _collect(stream, bucket: list[str], merged: list[str]) -> None:
    try:
        for line in iter(stream.readline, ""):
            bucket.append(line)
            merged.append(line)
            if len(merged) > 2000:          # a chatty server can't grow this forever
                del merged[:1000]
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _join(readers: list[threading.Thread]) -> None:
    """Let the readers catch up. Bounded: a child left running in the
    background can hold the pipe open, and its output isn't this command's."""
    for reader in readers:
        reader.join(timeout=2.0)


def _adopt(process: subprocess.Popen, command: str, workdir: str, merged: list[str]) -> None:
    """Keep a command that turned out to be a server running, as one of the
    background processes: listed, read and stopped like the others."""
    with _processes_lock:
        _processes[process.pid] = {
            "pid": process.pid,
            "command": command,
            "cwd": workdir,
            "process": process,
            "output": merged,
            "started_at": time.time(),
        }


# ============================================================
# Background processes
# ============================================================

# Processes Mike started and can still reason about. Without this a
# background process was fire-and-forget: started, given a pid, then
# invisible — no way to tell whether a dev server was still up, read why it
# died, or stop it. That made "start a server and verify it" unanswerable.
_processes: dict[int, dict] = {}
_REAP_AFTER_SECONDS = 300   # keep recent exits visible, forget ancient ones
_processes_lock = threading.Lock()


def _drain(pid: int, stream) -> None:
    """Continuously collects a background process's output so it can be read
    later. Without a reader the OS pipe buffer fills and the process blocks
    forever once it has printed enough — a hang Mike would have caused."""
    try:
        for line in iter(stream.readline, ""):
            with _processes_lock:
                entry = _processes.get(pid)
                if entry is None:
                    return
                entry["output"].append(line)
                # Bounded so a chatty server can't grow memory without limit.
                if len(entry["output"]) > 2000:
                    del entry["output"][:1000]
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


class _EditorRun:
    """A command running in a terminal in the student's VS Code, looked after
    like one of Mike's own: listed, read and stopped through the editor. It
    answers the few questions the registry asks a Popen."""

    #: How long one look at it is trusted before asking the editor again.
    FRESH = 1.0

    def __init__(self, window: str, run_id: str, pid: int, terminal: str) -> None:
        self.window, self.run_id, self.pid, self.terminal = window, run_id, pid, terminal
        self.returncode: int | None = None
        self._state: dict = {"running": True}
        self._seen = 0.0
        self._ended = False

    def _look(self) -> dict:
        if self._ended or time.monotonic() - self._seen < self.FRESH:
            return self._state
        from ide import manager
        state = manager.run_output(self.window, self.run_id)
        self._seen = time.monotonic()
        if state.get("ok"):
            self._state = state
            if not state.get("running"):
                self.returncode = state.get("exitCode")
                self._ended = True
        return self._state

    def poll(self) -> int | None:
        if self._look().get("running"):
            return None
        # Ended with no code the shell reported (stopped, or its terminal
        # closed): not a success to report as 0.
        return self.returncode if self.returncode is not None else -1

    def output(self) -> str:
        return _clip(str(self._look().get("output") or "").strip())

    def stop(self) -> None:
        from ide import manager
        result = manager.stop_run(self.window, self.run_id)
        if result.get("ok"):
            self._state, self._ended = result, True
            self.returncode = result.get("exitCode")


#: Ids for editor runs whose shell didn't say its process id.
_editor_ids = itertools.count(900_001)

#: How long a new background process is watched before it's reported as up
#: -- long enough to catch one that fails on startup.
_SETTLE_SECONDS = 2.5


def _run_in_editor(command: str, workdir: str) -> dict | None:
    """Start it in the student's VS Code terminal, when one is connected: a
    dev server Mike starts is theirs to watch, read and stop, beside their
    code -- not a process out of sight. None to run it the hidden way."""
    try:
        from ide import manager
        started = manager.run_in_terminal(command, workdir, wait=_SETTLE_SECONDS)
    except Exception:
        logger.exception("Could not start %r in the editor.", command)
        return None
    if not started:
        return None
    pid = started.get("pid")
    run = _EditorRun(str(started.get("window") or ""), str(started.get("id") or ""),
                     pid if isinstance(pid, int) else next(_editor_ids),
                     str(started.get("terminal") or ""))
    with _processes_lock:
        _processes[run.pid] = {
            "pid": run.pid,
            "command": command,
            "cwd": workdir,
            "process": run,
            "output": [],
            "started_at": time.time(),
            "editor": True,
        }
    result = {"pid": run.pid, "command": command, "cwd": workdir,
              "output": _clip(str(started.get("output") or "").strip()),
              "where": (f"In the {run.terminal!r} terminal in their VS Code, "
                        "where they can watch it and stop it themselves.")}
    if started.get("running"):
        return {**result, "running": True}
    run.returncode = started.get("exitCode")
    run._state, run._ended = started, True
    return {**result, "running": False, "exit_code": started.get("exitCode")}


def run_background(command: str, cwd: str | None = None) -> dict:
    """
    Start a long-running process (a server, a watcher) and return immediately.

    The process is detached so it outlives this call; a short settle window
    catches commands that fail on startup rather than reporting a false
    success. Registered so it can be listed, read, and killed afterwards.
    With the student's VS Code connected it runs in a terminal there instead.
    """

    if not command.strip():
        raise ValueError("Command cannot be empty.")

    workdir = cwd or os.getcwd()
    logger.info("Starting background command: %s (cwd=%s)", command, workdir)

    shown = _run_in_editor(command, workdir)
    if shown is not None:
        return shown

    # spawn_detached groups the process (its own session on POSIX, its own
    # process group on Windows) so kill_process can stop the whole tree
    # later, not just this shell.
    process = processes.spawn_detached(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )

    with _processes_lock:
        _processes[process.pid] = {
            "pid": process.pid,
            "command": command,
            "cwd": workdir,
            "process": process,
            "output": [],
            "started_at": time.time(),
        }

    if process.stdout is not None:
        threading.Thread(
            target=_drain, args=(process.pid, process.stdout), daemon=True
        ).start()

    # If it dies immediately, that's a failure worth reporting now.
    deadline = time.monotonic() + _SETTLE_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        time.sleep(0.05)

    if process.poll() is None:
        return {
            "pid": process.pid,
            "running": True,
            "command": command,
            "cwd": workdir,
            "output": _recent_output(process.pid),
        }

    return {
        "pid": process.pid,
        "running": False,
        "exit_code": process.returncode,
        "command": command,
        "cwd": workdir,
        "output": _recent_output(process.pid),
    }


def _recent_output(pid: int, limit: int = 200) -> str:
    with _processes_lock:
        entry = _processes.get(pid)
        if entry is None:
            return ""
        if entry.get("editor"):
            process = entry["process"]
        else:
            lines = entry["output"][-limit:]
    if entry.get("editor"):
        return "\n".join(process.output().splitlines()[-limit:])
    return _clip("".join(lines).strip())


def list_processes() -> dict:
    """Every background process Mike started this session, and whether it is
    still alive — so 'is the dev server up?' is an observation, not a guess."""
    out = []
    with _processes_lock:
        entries = list(_processes.values())

    reap = []
    for entry in entries:
        process = entry["process"]
        alive = process.poll() is None
        finished_for = 0 if alive else time.time() - entry.get("ended_at", entry["started_at"])
        # A process that exited long ago is history, not state. Left in the
        # registry they accumulate for the life of the session, so every
        # listing grows and the model has to re-read a list of things that
        # are not running to find the one that is.
        if not alive and finished_for > _REAP_AFTER_SECONDS:
            reap.append(entry["pid"])
            continue
        if not alive:
            entry.setdefault("ended_at", time.time())
        out.append({
            "pid": entry["pid"],
            "command": entry["command"],
            "cwd": entry["cwd"],
            "running": alive,
            "exit_code": None if alive else process.returncode,
            "uptime_seconds": round(time.time() - entry["started_at"]),
        })

    if reap:
        with _processes_lock:
            for pid in reap:
                _processes.pop(pid, None)

    running = [p for p in out if p["running"]]
    if not out:
        summary = "No background processes are running."
    else:
        described = []
        for entry in out:
            state = "running" if entry["running"] else f"exited ({entry['exit_code']})"
            described.append(f"pid {entry['pid']} {state}: {entry['command'][:60]}")
        summary = f"{len(running)} running of {len(out)}:\n" + "\n".join(described)

    # Same key every other tool reports under, so the activity log describes
    # what happened instead of showing "Done".
    return {"processes": out, "count": len(out), "result": summary}


def process_output(pid: int, limit: int = 200) -> dict:
    """Read what a background process has printed — the actual way to find
    out why a server failed to come up, or confirm that it did."""
    with _processes_lock:
        entry = _processes.get(pid)
        if entry is None:
            return {"error": f"No background process with pid {pid} was started by Mike."}
        process = entry["process"]
        alive = process.poll() is None
        code = None if alive else process.returncode

    return {
        "pid": pid,
        "running": alive,
        "exit_code": code,
        "output": _recent_output(pid, limit),
    }


def kill_process(pid: int) -> dict:
    """Stop a process Mike started. Scoped to Mike's own registry on purpose:
    this is not a general 'kill any pid on the machine' capability."""
    with _processes_lock:
        entry = _processes.get(pid)
        if entry is None:
            return {"error": f"No background process with pid {pid} was started by Mike."}
        process = entry["process"]

    if process.poll() is not None:
        return {"pid": pid, "running": False, "result": "It had already exited."}

    try:
        if entry.get("editor"):
            # In the student's VS Code terminal: stopped there (Ctrl+C, then
            # the terminal closed if that isn't enough).
            process.stop()
            return {"pid": pid, "running": False, "result": f"Stopped pid {pid} in their VS Code terminal."}
        # process was started with spawn_detached, so it leads its own
        # group/session — terminate_tree stops that whole group, which is
        # what actually reaches children a shell spawned (a dev server's
        # real node process, for instance), on both POSIX and Windows.
        processes.terminate_tree(process, timeout=5)
    except Exception as exc:
        return {"error": f"Could not stop pid {pid}: {exc}"}

    return {"pid": pid, "running": False, "result": f"Stopped pid {pid}."}


def shutdown_all() -> None:
    """Called at app teardown so Mike doesn't leave orphaned servers behind.
    What runs in the student's VS Code terminal isn't an orphan: it's there
    in front of them, and stays theirs to stop."""
    with _processes_lock:
        pids = [pid for pid, entry in _processes.items() if not entry.get("editor")]
    for pid in pids:
        try:
            kill_process(pid)
        except Exception:
            pass
    # Clear the registry too. The processes were being killed correctly, but
    # their entries stayed, so a listing after teardown still described three
    # dead servers as though they were part of the session's state.
    with _processes_lock:
        _processes.clear()
