from __future__ import annotations

import subprocess

from logs.logger import logger


def run(command: str) -> str:
    """
    Execute a shell command and return stdout.

    Raises:
        RuntimeError: if the command exits with a non-zero status.
    """

    if not command.strip():
        raise ValueError("Command cannot be empty.")

    logger.info(f"Running command: {command}")

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or
            "Command failed."
        )

    return result.stdout.strip()