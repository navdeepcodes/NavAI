from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SkillResult:
    """
    Result returned by every skill.
    """

    handled: bool

    skill_name: str = ""

    confidence: float = 1.0

    response: str = ""

    metadata: dict[str, Any] = field(
        default_factory=dict,
    )