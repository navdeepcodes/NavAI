from __future__ import annotations

from logs.logger import logger

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.provider_policy import ProviderPolicy
from brain.providers.provider_registry import ProviderRegistry
from brain.providers.provider_selector import ProviderSelector

from brain.providers.gemini_provider import GeminiProvider
from brain.providers.groq_provider import GroqProvider
from brain.providers.ollama_provider import OllamaProvider
from brain.providers.openrouter_provider import OpenRouterProvider


class ProviderManager:
    """
    Central coordinator for every LLM provider.

    Responsibilities
    ----------------
    • Discover providers
    • Register providers
    • Model lookup
    • Expose routing components

    Never
    -----
    • Execute requests
    • Build prompts
    • Parse responses
    """

    # =====================================================

    def __init__(self) -> None:

        logger.info(
            "Initializing Provider Manager..."
        )

        self.registry = ProviderRegistry()

        self.policy = ProviderPolicy(
            self.registry
        )

        self.selector = ProviderSelector(
            self.registry
        )

        self.reload()

    # =====================================================

    def reload(self) -> None:

        self.registry.clear()

        self._discover()

    # =====================================================

    def _discover(self) -> None:

        candidates = (

            GroqProvider(),

            OllamaProvider(),

            OpenRouterProvider(),

            GeminiProvider(),

        )

        for provider in candidates:

            logger.info(
                "Checking provider '%s'...",
                provider.name,
            )

            try:

                if not provider.health_check():

                    logger.warning(
                        "Skipping '%s' (health check failed).",
                        provider.name,
                    )

                    continue

            except Exception:

                logger.exception(
                    "Failed initializing '%s'",
                    provider.name,
                )

                continue

            self.registry.register(
                provider
            )

        if len(self.registry) == 0:

            raise RuntimeError(
                "No LLM providers are available."
            )

    # =====================================================

    def provider(
        self,
        task: str = "general",
    ) -> BaseLLMProvider:
        """
        Return the provider selected for this task.
        """

        candidates = self.policy.providers_for(
            task
        )

        return self.selector.select(
            candidates
        )

    # =====================================================

    def providers(
        self,
        task: str = "general",
    ) -> list[BaseLLMProvider]:
        """
        Return providers in routing priority order.

        Used by LLMService for automatic fallback.
        """

        providers: list[BaseLLMProvider] = []

        for name in self.policy.providers_for(task):

            try:

                providers.append(
                    self.get(name)
                )

            except ValueError:

                continue

        return providers

    # =====================================================

    def mark_success(
        self,
        provider_name: str,
        latency_ms: float,
    ) -> None:

        self.selector.report_success(
            provider_name,
            latency_ms,
        )

    # =====================================================

    def mark_failure(
        self,
        provider_name: str,
    ) -> None:

        self.selector.report_failure(
            provider_name
        )

    # =====================================================

    def provider_names(
        self,
    ) -> tuple[str, ...]:

        return self.registry.names()

    # =====================================================

    def provider_count(
        self,
    ) -> int:

        return len(self.registry)

    # =====================================================

    def has_provider(
        self,
        name: str,
    ) -> bool:

        return self.registry.exists(
            name
        )

    # =====================================================

    def get(
        self,
        name: str,
    ) -> BaseLLMProvider:

        return self.registry.get(
            name
        ).provider

    # =====================================================

    def by_model(
        self,
        model: str,
    ) -> BaseLLMProvider:

        model = model.lower()

        if "gemini" in model:

            return self.get(
                "Gemini"
            )

        if (
            "gpt" in model
            or
            "openrouter" in model
        ):

            return self.get(
                "OpenRouter"
            )

        if (
            "llama" in model
            or "qwen" in model
            or "mistral" in model
            or "deepseek" in model
            or "phi" in model
        ):

            if self.has_provider(
                "Ollama"
            ):

                return self.get(
                    "Ollama"
                )

            return self.get(
                "Groq"
            )

        if "groq" in model:

            return self.get(
                "Groq"
            )

        return self.provider()

    # =====================================================

    @property
    def current_provider(
        self,
    ) -> BaseLLMProvider | None:

        return self.selector.current()