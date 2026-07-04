from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """
    Lifecycle of an executable task.

    Every task moves through these states exactly once.
    """

    PENDING = "pending"

    READY = "ready"

    RUNNING = "running"

    COMPLETED = "completed"

    FAILED = "failed"

    CANCELLED = "cancelled"

    SKIPPED = "skipped"

    RETRYING = "retrying"