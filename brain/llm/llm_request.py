from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from uuid import uuid4


@dataclass(slots=True, frozen=True)
class LLMRequest:
    """
    Provider-agnostic request.

    This is the only object exchanged between Mike's
    intelligence layer and provider layer.
    """

    # =====================================================
    # Prompt
    # =====================================================

    system_prompt: str

    user_input: str

    # =====================================================
    # Model
    # =====================================================

    model: str | None = None

    # =====================================================
    # Generation
    # =====================================================

    temperature: float = 0.2

    top_p: float | None = None

    max_tokens: int | None = None

    stop_sequences: Sequence[str] = field(
        default_factory=tuple,
    )

    stream: bool = False

    timeout: float | None = None

    # =====================================================
    # Optional
    # =====================================================

    parser: Any | None = None

    image: str |None = None

    tools: bool = False

    # =====================================================
    # Metadata
    # =====================================================

    request_id: str = field(
        default_factory=lambda: str(uuid4()),
    )

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    # =====================================================

    @property
    def task(self) -> str:
        """
        Convenience accessor.
        """

        return str(
            self.metadata.get(
                "task",
                "general",
            )
        )

    # =====================================================

    def __post_init__(self) -> None:

        if not self.system_prompt.strip():
            raise ValueError(
                "system_prompt cannot be empty."
            )

        if not self.user_input.strip():
            raise ValueError(
                "user_input cannot be empty."
            )

        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                "temperature must be between 0 and 2."
            )

        if (
            self.top_p is not None
            and not 0.0 < self.top_p <= 1.0
        ):
            raise ValueError(
                "top_p must be between 0 and 1."
            )

        if (
            self.max_tokens is not None
            and self.max_tokens <= 0
        ):
            raise ValueError(
                "max_tokens must be > 0."
            )

        if any(
            not isinstance(x, str)
            for x in self.stop_sequences
        ):
            raise TypeError(
                "stop_sequences must contain strings."
            )