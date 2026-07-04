from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from brain.planning.task_status import TaskStatus


@dataclass(slots=True)
class Task:
    """
    Represents one executable operation.

    Tasks are produced by the Planner and consumed by the
    Executor. They contain execution information only and
    never perform reasoning.
    """

    # =====================================================
    # Identity
    # =====================================================

    id: str = field(
        default_factory=lambda: uuid4().hex
    )

    created_at: datetime = field(
        default_factory=datetime.utcnow
    )

    # =====================================================
    # Execution
    # =====================================================

    tool: str = ""

    action: str = ""

    arguments: dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================
    # Planning
    # =====================================================

    description: str = ""

    priority: int = 0

    depends_on: list[str] = field(
        default_factory=list
    )

    # =====================================================
    # Runtime
    # =====================================================

    status: TaskStatus = TaskStatus.PENDING

    started_at: datetime | None = None

    finished_at: datetime | None = None

    # =====================================================
    # Result
    # =====================================================

    result: Any = None

    error: str | None = None

    retries: int = 0

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================
    # Properties
    # =====================================================

    @property
    def executable(self) -> bool:

        return bool(self.tool and self.action)

    # -----------------------------------------------------

    @property
    def successful(self) -> bool:

        return self.status is TaskStatus.COMPLETED

    # -----------------------------------------------------

    @property
    def failed(self) -> bool:

        return self.status is TaskStatus.FAILED

    # =====================================================
    # State Management
    # =====================================================

    def start(self) -> None:

        self.status = TaskStatus.RUNNING

        self.started_at = datetime.utcnow()

    # -----------------------------------------------------

    def complete(
        self,
        result: Any = None,
    ) -> None:

        self.status = TaskStatus.COMPLETED

        self.finished_at = datetime.utcnow()

        self.result = result

        self.error = None

    # -----------------------------------------------------

    def fail(
        self,
        error: Exception | str,
    ) -> None:

        self.status = TaskStatus.FAILED

        self.finished_at = datetime.utcnow()

        self.error = str(error)

    # -----------------------------------------------------

    def retry(self) -> None:

        self.retries += 1

        self.status = TaskStatus.RETRYING

    # -----------------------------------------------------

    def cancel(self) -> None:

        self.status = TaskStatus.CANCELLED

        self.finished_at = datetime.utcnow()

    # -----------------------------------------------------

    def skip(self) -> None:

        self.status = TaskStatus.SKIPPED

        self.finished_at = datetime.utcnow()