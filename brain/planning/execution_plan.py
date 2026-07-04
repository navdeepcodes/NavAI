from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from brain.planning.task import Task
from brain.planning.task_status import TaskStatus


@dataclass(slots=True)
class ExecutionPlan:
    """
    A complete execution plan for a single user request.
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
    # Goal
    # =====================================================

    goal: str = ""

    # =====================================================
    # Tasks
    # =====================================================

    tasks: list[Task] = field(
        default_factory=list
    )

    # =====================================================
    # Runtime
    # =====================================================

    current_task: int = 0

    metadata: dict[str, object] = field(
        default_factory=dict
    )

    # =====================================================
    # Helpers
    # =====================================================

    def add_task(
        self,
        task: Task,
    ) -> None:

        self.tasks.append(task)

    # -----------------------------------------------------

    @property
    def empty(self) -> bool:

        return not self.tasks

    # -----------------------------------------------------

    @property
    def finished(self) -> bool:

        return all(
            task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.SKIPPED,
                TaskStatus.CANCELLED,
            )
            for task in self.tasks
        )

    # -----------------------------------------------------

    @property
    def successful(self) -> bool:

        return (
            not self.empty
            and all(
                task.status == TaskStatus.COMPLETED
                for task in self.tasks
            )
        )

    # -----------------------------------------------------

    @property
    def pending_tasks(self) -> list[Task]:

        return [
            task
            for task in self.tasks
            if task.status == TaskStatus.PENDING
        ]

    # -----------------------------------------------------

    @property
    def running_tasks(self) -> list[Task]:

        return [
            task
            for task in self.tasks
            if task.status == TaskStatus.RUNNING
        ]

    # -----------------------------------------------------

    @property
    def completed_tasks(self) -> list[Task]:

        return [
            task
            for task in self.tasks
            if task.status == TaskStatus.COMPLETED
        ]

    # -----------------------------------------------------

    @property
    def progress(self) -> float:

        if self.empty:
            return 0.0

        return len(self.completed_tasks) / len(self.tasks)

    # -----------------------------------------------------

    @property
    def next_task(self) -> Task | None:

        for task in self.tasks:

            if task.status == TaskStatus.PENDING:

                return task

        return None