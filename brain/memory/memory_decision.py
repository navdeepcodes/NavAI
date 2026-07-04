from __future__ import annotations

from dataclasses import dataclass, field

from brain.memory.memory_types import MemoryType


@dataclass(slots=True)
class MemoryDecision:
    """
    Represents the outcome of Mike's memory evaluation.

    Every conversation is first evaluated before
    becoming a long-term memory.
    """

    should_store: bool = False

    memory_type: MemoryType = MemoryType.EPISODIC

    importance: float = 0.0

    summary: str = ""

    reason: str = ""

    tags: list[str] = field(default_factory=list)

    relationships: list[str] = field(default_factory=list)

    confidence: float = 1.0