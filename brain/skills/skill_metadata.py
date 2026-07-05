from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SkillMetadata:

    name: str

    description: str

    category: str

    priority: int = 100

    examples: list[str] = field(
        default_factory=list,
    )