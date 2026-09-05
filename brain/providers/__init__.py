"""Choosing which brain Mike is thinking with.

One place resolves configuration into a provider, so that adding Anthropic,
OpenAI, or an OpenAI-compatible endpoint later means adding a module here and
a name in config — not touching the runtime, the tools, or the UI.

Mike's identity, memory, projects, and safety are unaffected by this choice.
The brain is replaceable; Mike is the constant.
"""
from __future__ import annotations

from brain.providers.base import (
    BrainError,
    BrainProvider,
    BrainUnavailable,
    Capabilities,
    ChatResult,
    StreamEvent,
    ToolCall,
    estimate_tokens,
)

__all__ = [
    "BrainError",
    "BrainProvider",
    "BrainUnavailable",
    "Capabilities",
    "ChatResult",
    "StreamEvent",
    "ToolCall",
    "estimate_tokens",
    "get_provider",
    "available_providers",
]

_CACHE: dict[str, BrainProvider] = {}


# Every brain Mike can construct, as configuration rather than code.
# Adding a backend means adding a row here — not touching the runtime, the
# tools, the safety gates, or the UI.
_ENDPOINTS: dict[str, dict] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-v4-flash",
        "vision_model": "deepseek-v4-flash-vision-exp",
        "context_tokens": 65536,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "default_model": "deepseek/deepseek-v4-flash",
        "context_tokens": 65536,
        "extra_headers": {"HTTP-Referer": "https://github.com/mike", "X-Title": "Mike"},
    },
    "gemini": {
        # Google exposes an OpenAI-compatible surface, so Gemini needs no
        # separate provider implementation either.
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        # Discovered, not assumed: the endpoint reports that gemini-2.5-flash
        # "is no longer available to new users" and directs callers to this
        # model instead. Gemini 3.x also reasons before answering, spending
        # tokens invisibly — too small a max_tokens returns an empty message
        # with completion_tokens=0, so the provider default of 900 matters.
        "default_model": "gemini-3.6-flash",
        "vision_model": "gemini-3.6-flash",
        # Google's /models listing carries no input-modality field, so
        # capability detection cannot infer this the way OpenRouter's does.
        # Declared here and still subject to the probe — a declaration, not a
        # conclusion.
        "declared_vision": True,
        "context_tokens": 1048576,
    },
}


def available_providers() -> list[str]:
    """Providers Mike can construct today. Grows as rows are added above; the
    rest of Mike does not change when it does."""
    return ["ollama", *sorted(_ENDPOINTS)]


def get_provider(
    *,
    provider: str | None = None,
    model: str | None = None,
    vision_model: str | None = None,
    refresh: bool = False,
) -> BrainProvider:
    """The brain for this session.

    Defaults come from config so existing behaviour is unchanged, but every
    part is overridable — which is what makes runtime model switching a
    configuration change rather than a code change.
    """
    from config import ollama as ollama_config

    provider = (provider or getattr(ollama_config, "BRAIN_PROVIDER", "ollama")).lower()
    if provider == "ollama":
        model = model or ollama_config.OLLAMA_CHAT_MODEL
        vision_model = vision_model or ollama_config.OLLAMA_VISION_MODEL

    key = f"{provider}:{model}:{vision_model}"
    if not refresh and key in _CACHE:
        return _CACHE[key]

    if provider == "ollama":
        from brain.providers.ollama_provider import OllamaProvider

        instance: BrainProvider = OllamaProvider(
            model=model,
            host=ollama_config.OLLAMA_HOST,
            num_ctx=getattr(ollama_config, "NUM_CTX", 8192),
            vision_model=vision_model,
        )
    elif provider in _ENDPOINTS:
        from brain.providers.openai_compatible import OpenAICompatibleProvider

        spec = _ENDPOINTS[provider]
        instance = OpenAICompatibleProvider(
            model=model or spec["default_model"],
            base_url=spec["base_url"],
            api_key_env=spec["api_key_env"],
            name=provider,
            vision_model=vision_model or spec.get("vision_model"),
            context_tokens=spec.get("context_tokens", 32768),
            extra_headers=spec.get("extra_headers"),
            declared_vision=spec.get("declared_vision"),
        )
    else:
        raise BrainUnavailable(
            f"Unknown brain provider {provider!r}. Available: "
            f"{', '.join(available_providers())}."
        )

    _CACHE[key] = instance
    return instance
