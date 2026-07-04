from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolResult:
    """
    Standard response returned by every tool.
    """

    success: bool

    tool: str

    action: str

    message: str = ""

    data: dict[str, Any] = field(
        default_factory=dict
    )

    error: str | None = None

    execution_time_ms: float = 0.0

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def failed(self) -> bool:
        return not self.success

    def __bool__(self) -> bool:
        return self.success