from __future__ import annotations

from dataclasses import dataclass, field

from brain.planning.models.planning_task import PlanningTask


@dataclass(slots=True)
class PlanningResult:
    """
    High-level execution plan.

    Produced by PlanningEngine.

    Consumed by Planner.
    """

    goal: str

    tasks: list[PlanningTask] = field(default_factory=list)

    reasoning: str = ""

    confidence: float = 1.0

    @property
    def requires_execution(self) -> bool:
        return bool(self.tasks)