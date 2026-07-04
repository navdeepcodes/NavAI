from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LLMResponse:
    """
    Standardized response returned by the LLM layer.
    """

    success: bool

    text: str

    parsed: Any | None = None

    model: str = ""

    latency_ms: float = 0.0

    prompt_tokens: int = 0

    completion_tokens: int = 0

    total_tokens: int = 0

    finish_reason: str = ""

    metadata: dict[str, Any] = field(
        default_factory=dict
    )