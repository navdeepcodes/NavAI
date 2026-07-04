from __future__ import annotations

from brain.providers.provider_registry import ProviderRegistry


class ProviderPolicy:
    """
    Routing policy for LLM providers.

    Responsibilities
    ----------------
    • Define provider priorities.
    • Return provider order for a task.
    • Allow runtime overrides.

    Never
    -----
    • Execute requests.
    • Check provider health.
    • Track provider state.
    """

    _DEFAULT_PRIORITIES = {

        "conversation": [
            "Groq",
            "Ollama",
            "OpenRouter",
            "Gemini",
        ],

        "reasoning": [
            "OpenRouter",
            "Gemini",
            "Groq",
            "Ollama",
        ],

        "coding": [
            "Groq",
            "OpenRouter",
            "Ollama",
            "Gemini",
        ],

        "vision": [
            "Gemini",
            "OpenRouter",
            "Ollama",
        ],

        "general": [
            "Groq",
            "Ollama",
            "OpenRouter",
            "Gemini",
        ],

    }

    # =====================================================

    def __init__(
        self,
        registry: ProviderRegistry,
    ) -> None:

        self._registry = registry

        self._priorities = {
            task: providers.copy()
            for task, providers
            in self._DEFAULT_PRIORITIES.items()
        }

    # =====================================================

    def providers_for(
        self,
        task: str,
    ) -> list[str]:

        return self._priorities.get(
            task,
            self._priorities["general"],
        ).copy()

    # =====================================================

    def priority(
        self,
        task: str,
    ) -> tuple[str, ...]:

        return tuple(
            self.providers_for(task)
        )

    # =====================================================

    def has_task(
        self,
        task: str,
    ) -> bool:

        return task in self._priorities

    # =====================================================

    def tasks(
        self,
    ) -> tuple[str, ...]:

        return tuple(
            self._priorities.keys()
        )

    # =====================================================

    def set_priority(
        self,
        task: str,
        providers: list[str],
    ) -> None:

        self._priorities[task] = providers.copy()

    # =====================================================

    def reset(
        self,
    ) -> None:

        self._priorities = {
            task: providers.copy()
            for task, providers
            in self._DEFAULT_PRIORITIES.items()
        }

    # =====================================================

    def priority_map(
        self,
    ) -> dict[str, list[str]]:

        return {
            task: providers.copy()
            for task, providers
            in self._priorities.items()
        }