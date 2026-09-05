from __future__ import annotations

import os
import signal
import subprocess
import threading
import time

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

    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        # Partial output is often the whole diagnosis for a hang (where it got
        # stuck), so it's returned rather than thrown away with the exception.
        return {
            "exit_code": None,
            "timed_out": True,
            "timeout_seconds": timeout,
            "stdout": _clip(_decode(exc.stdout)),
            "stderr": _clip(_decode(exc.stderr)),
            "cwd": workdir,
            "command": command,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
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

    return {
        "exit_code": completed.returncode,
        "timed_out": False,
        "stdout": _clip(completed.stdout),
        "stderr": _clip(completed.stderr),
        "cwd": workdir,
        "command": command,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def _decode(stream) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", errors="replace")
    return str(stream)


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


def run_background(command: str, cwd: str | None = None) -> dict:
    """
    Start a long-running process (a server, a watcher) and return immediately.

    The process is detached so it outlives this call; a short settle window
    catches commands that fail on startup rather than reporting a false
    success. Registered so it can be listed, read, and killed afterwards.
    """

    if not command.strip():
        raise ValueError("Command cannot be empty.")

    workdir = cwd or os.getcwd()
    logger.info("Starting background command: %s (cwd=%s)", command, workdir)

    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        start_new_session=True,
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
    settle = 2.5
    deadline = time.monotonic() + settle
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
        lines = entry["output"][-limit:]
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
        # The process was started with start_new_session=True, so it leads its
        # own group — killing the group also stops children a shell spawned
        # (a dev server's actual node process, for instance).
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception:
        try:
            process.terminate()
        except Exception as exc:
            return {"error": f"Could not stop pid {pid}: {exc}"}

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            process.kill()

    return {"pid": pid, "running": False, "result": f"Stopped pid {pid}."}


def shutdown_all() -> None:
    """Called at app teardown so Mike doesn't leave orphaned servers behind."""
    with _processes_lock:
        pids = list(_processes.keys())
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
