from brain.providers.gemini_provider import GeminiProvider
from brain.providers.openrouter_provider import OpenRouterProvider


def get_vision_provider():

    # Try Gemini first
    try:

        provider = GeminiProvider()

        if provider.health_check():

            return provider

    except Exception:
        pass

    # Fallback to OpenRouter
    try:

        return OpenRouterProvider()

    except Exception:
        pass

    raise RuntimeError(
        "No vision provider available."
    )