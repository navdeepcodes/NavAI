from dataclasses import dataclass


@dataclass(slots=True)
class ProviderResponse:

    text: str

    provider: str

    model: str = ""

    finish_reason: str | None = None

    input_tokens: int = 0

    output_tokens: int = 0

    latency_ms: float = 0.0

    raw: object | None = None