from __future__ import annotations

from brain.providers import manager
from brain.providers.base_llm_provider import BaseLLMProvider


class ProviderRouter:
    """
    Provider routing layer.

    Responsibilities
    ----------------
    • Route requests to the appropriate provider(s).
    • Translate request requirements into provider selection.
    • Hide ProviderManager from the LLM layer.

    Never
    -----
    • Execute LLM requests.
    • Track provider health.
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
        Return the single best provider for this request.
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
        Return providers ordered by routing preference.

        The ProviderManager already accounts for provider
        availability and health. The router simply exposes
        the ordered list to the execution layer.
        """

        if model is not None:

            return [
                manager.by_model(model)
            ]

        return manager.providers(task)

    # =====================================================

    def default(
        self,
    ) -> BaseLLMProvider:
        """
        Convenience helper for general-purpose requests.
        """

        return manager.provider()

    # =====================================================

    def available(
        self,
    ) -> tuple[str, ...]:
        """
        Return currently registered providers.
        """

        return manager.provider_names()