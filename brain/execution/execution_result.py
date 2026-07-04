from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ExecutionResult:
    """
    Result of executing a single task.
    """

    success: bool

    message: str = ""

    data: Any = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    error: str | None = None