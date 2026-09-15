from __future__ import annotations

import os
import signal
import subprocess

from logs.logger import logger

# Commands that finish are expected to finish reasonably quickly. Anything
# that doesn't is either stuck or is really a long-running process, which
# belongs in run_background instead.
DEFAULT_TIMEOUT = 60

# subprocess.run(shell=True, timeout=...) only kills the shell it spawns —
# a child the shell started (e.g. `sleep 999` under `sh -c`) is orphaned and
# keeps running. Starting the shell in its own process group and killing the
# whole group on timeout closes that leak. POSIX-only (no killpg on Windows).
_HAS_PROCESS_GROUPS = hasattr(os, "killpg") and hasattr(os, "setsid")


def run(command: str, cwd: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> str:
    """
    Execute a shell command and return stdout.

    Raises:
        RuntimeError: if the command fails or outlives its timeout.
    """

    if not command.strip():
        raise ValueError("Command cannot be empty.")

    logger.info(f"Running command: {command}")

    popen_kwargs = {"start_new_session": True} if _HAS_PROCESS_GROUPS else {}

    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        **popen_kwargs,
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if _HAS_PROCESS_GROUPS:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.communicate()
        raise RuntimeError(
            f"The command was still running after {timeout}s and was stopped. "
            "If it's a server or another process meant to keep running, "
            "start it in the background instead."
        )

    if process.returncode != 0:
        raise RuntimeError(
            stderr.strip() or
            "Command failed."
        )

    return stdout.strip()


def run_background(command: str, cwd: str | None = None) -> str:
    """
    Start a long-running process (a server, a watcher) and return immediately.

    The process is detached so it outlives this call; a short settle window
    catches commands that fail on startup rather than reporting a false success.
    """

    if not command.strip():
        raise ValueError("Command cannot be empty.")

    logger.info(f"Starting background command: {command}")

    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        start_new_session=True,
    )

    try:
        # If it dies immediately, that's a failure worth reporting now.
        process.wait(timeout=2.5)
    except subprocess.TimeoutExpired:
        where = f" in {cwd}" if cwd else ""
        return (
            f"Started in the background{where} (pid {process.pid}) and it's "
            f"still running: {command}"
        )

    output = ""
    if process.stdout:
        output = (process.stdout.read() or "").strip()[:800]

    raise RuntimeError(
        f"The process exited immediately with code {process.returncode}. "
        f"Output: {output or '(none)'}"
    )