from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlanningTask:
    """
    A single executable step produced by the Planning Engine.
    """

    tool: str

    action: str

    arguments: dict[str, Any] = field(default_factory=dict)

    description: str = ""

    priority: int = 0