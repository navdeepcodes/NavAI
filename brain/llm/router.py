from __future__ import annotations

from brain.provider import manager
from brain.providers.base_llm_provider import BaseLLMProvider


class ProviderRouter:
    """
    Routes LLM requests to the appropriate providers.

    Responsibilities
    ----------------
    • Return a single provider when explicitly requested.
    • Return an ordered provider list for automatic fallback.
    • Hide ProviderManager from LLMService.

    Never
    -----
    • Execute requests.
    • Perform health checks.
    • Maintain provider state.
    """

    # =====================================================

    def provider(
        self,
        *,
        task: str = "general",
        model: str | None = None,
    ) -> BaseLLMProvider:
        """
        Return the provider that should execute
        the next request.
        """

        if model is not None:
            return manager.by_model(model)

        return manager.provider(task)

    # =====================================================

    def providers(
        self,
        *,
        task: str = "general",
        model: str | None = None,
    ) -> list[BaseLLMProvider]:
        """
        Return providers in routing priority order.

        If a model is explicitly requested,
        only that provider is returned.
        """

        if model is not None:
            return [
                manager.by_model(model)
            ]

        return manager.providers(task)