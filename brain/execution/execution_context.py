from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ExecutionContext:
    """
    Shared execution state.

    Every tool receives the same context instance.
    """

    variables: dict[str, Any] = field(
        default_factory=dict
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    cancelled: bool = False

    def set(
        self,
        key: str,
        value: Any,
    ) -> None:

        self.variables[key] = value

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:

        return self.variables.get(
            key,
            default,
        )