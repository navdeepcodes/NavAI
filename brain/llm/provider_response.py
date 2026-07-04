from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProviderResponse:
    """
    Provider-agnostic response returned by every LLM provider.

    This class isolates the rest of Mike from provider-specific
    SDKs and response formats.

    Every provider (Gemini, Groq, OpenRouter, Ollama, etc.)
    converts its native response into this object.
    """

    # =====================================================
    # Generated Content
    # =====================================================

    text: str

    # =====================================================
    # Provider Information
    # =====================================================

    provider: str

    model: str | None = None

    # =====================================================
    # Performance
    # =====================================================

    latency_ms: float | None = None

    input_tokens: int | None = None

    output_tokens: int | None = None

    total_tokens: int | None = None

    finish_reason: str | None = None

    # =====================================================
    # Tool Calling
    # =====================================================

    tool_calls: list[Any] = field(
        default_factory=list
    )

    # =====================================================
    # Raw Provider Response
    # =====================================================

    raw: Any | None = None

    # =====================================================
    # Metadata
    # =====================================================

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================
    # Helpers
    # =====================================================

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def token_usage(self) -> int | None:
        if self.total_tokens is not None:
            return self.total_tokens

        if (
            self.input_tokens is not None
            and self.output_tokens is not None
        ):
            return self.input_tokens + self.output_tokens

        return None