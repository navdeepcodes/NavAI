from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from brain.memory.memory_types import MemoryType


@dataclass(slots=True)
class Memory:

    """
    Represents a single memory stored by Mike.
    """

    id: str = field(default_factory=lambda: str(uuid4()))

    type: MemoryType = MemoryType.EPISODIC

    title: str = ""

    content: str = ""

    summary: str = ""

    tags: list[str] = field(default_factory=list)

    entities: dict[str, Any] = field(default_factory=dict)

    metadata: dict[str, Any] = field(default_factory=dict)

    importance: float = 0.5

    confidence: float = 1.0

    created_at: datetime = field(default_factory=datetime.utcnow)

    updated_at: datetime = field(default_factory=datetime.utcnow)

    accessed_at: datetime = field(default_factory=datetime.utcnow)

    access_count: int = 0

    archived: bool = False

    source: str = "conversation"

    relationships: list[str] = field(default_factory=list)

    embedding: list[float] | None = None

    # -----------------------------------------------------

    def touch(self):

        self.accessed_at = datetime.utcnow()

        self.access_count += 1

    # -----------------------------------------------------

    def update(self):

        self.updated_at = datetime.utcnow()