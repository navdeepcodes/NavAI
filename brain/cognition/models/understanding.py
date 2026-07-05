from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Understanding:
    """
    Mike's understanding of a single user message.

    This object represents meaning only.

    It does not contain planning,
    execution,
    or response generation.

    Every user message produces exactly
    one Understanding.
    """

    # =====================================================
    # Core Understanding
    # =====================================================

    intent: str

    goal: str

    confidence: float

    # =====================================================
    # Conversation
    # =====================================================

    requires_context: bool = False

    referenced_entities: list[str] = field(
        default_factory=list
    )

    referenced_messages: list[str] = field(
        default_factory=list
    )

    # =====================================================
    # Information Completeness
    # =====================================================

    is_complete: bool = True

    missing_information: list[str] = field(
        default_factory=list
    )

    clarification: str | None = None

    # =====================================================
    # Memory
    # =====================================================

    requires_memory: bool = False

    memory_query: str | None = None

    # =====================================================
    # Emotion
    # =====================================================

    emotion: str = "neutral"

    tone: str = "neutral"

    # =====================================================
    # Metadata
    # =====================================================

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================
    # Convenience
    # =====================================================

    @property
    def needs_clarification(self) -> bool:
        return not self.is_complete

    @property
    def has_entities(self) -> bool:
        return bool(self.referenced_entities)

    @property
    def has_memory_request(self) -> bool:
        return self.requires_memory

    @property
    def has_context_dependency(self) -> bool:
        return self.requires_context