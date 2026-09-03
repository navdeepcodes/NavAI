from __future__ import annotations

import subprocess

from logs.logger import logger

# Commands that finish are expected to finish reasonably quickly. Anything
# that doesn't is either stuck or is really a long-running process, which
# belongs in run_background instead.
DEFAULT_TIMEOUT = 60


def run(command: str, cwd: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> str:
    """
    Execute a shell command and return stdout.

    Raises:
        RuntimeError: if the command fails or outlives its timeout.
    """

    if not command.strip():
        raise ValueError("Command cannot be empty.")

    logger.info(f"Running command: {command}")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"The command was still running after {timeout}s and was stopped. "
            "If it's a server or another process meant to keep running, "
            "start it in the background instead."
        )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or
            "Command failed."
        )

    return result.stdout.strip()


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