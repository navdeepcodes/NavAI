from dataclasses import dataclass


@dataclass(slots=True)
class ProviderCapability:

    name: str

    chat: bool = True

    vision: bool = False

    tools: bool = False

    streaming: bool = False

    reasoning_score: int = 5

    coding_score: int = 5

    speed_score: int = 5

    privacy_score: int = 5

    local: bool = False

    context_window: int = 32000

    cost_score: int = 5