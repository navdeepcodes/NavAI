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
    • Delegate provider selection
    • Expose provider lookup

    Does NOT:
    ----------
    • Execute requests
    • Maintain provider health
    • Decide provider scoring
    """

    def __init__(self) -> None:

        logger.info("Initializing Provider Manager...")

        self.registry = ProviderRegistry()

        self.policy = ProviderPolicy(self.registry)

        self.selector = ProviderSelector(self.registry)

        self.reload()

    # ---------------------------------------------------------

    def reload(self) -> None:

        self.registry.clear()

        self._discover()

        logger.info(
            "Provider Manager ready (%d providers).",
            len(self.registry),
        )

    # ---------------------------------------------------------

    def _candidate_providers(
        self,
    ) -> tuple[BaseLLMProvider, ...]:

        return (
            GroqProvider(),
            OllamaProvider(),
            OpenRouterProvider(),
            GeminiProvider(),
        )

    # ---------------------------------------------------------

    def _discover(self) -> None:

        for provider in self._candidate_providers():

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

                self.registry.register(provider)

                logger.info(
                    "Registered provider: %s",
                    provider.name,
                )

            except Exception:

                logger.exception(
                    "Failed initializing '%s'.",
                    provider.name,
                )

        if len(self.registry) == 0:

            raise RuntimeError(
                "No LLM providers are available."
            )

    # ---------------------------------------------------------

    def provider(
        self,
        task: str = "general",
    ) -> BaseLLMProvider:

        candidates = self.policy.providers_for(task)

        return self.selector.select(candidates)

    # ---------------------------------------------------------

    def providers(
        self,
        task: str = "general",
    ) -> list[BaseLLMProvider]:

        providers: list[BaseLLMProvider] = []

        for name in self.policy.providers_for(task):

            if self.registry.exists(name):

                providers.append(
                    self.registry.get(name).provider
                )

        return providers

    # ---------------------------------------------------------

    def mark_success(
        self,
        provider_name: str,
        latency_ms: float,
    ) -> None:

        self.selector.report_success(
            provider_name,
            latency_ms,
        )

    # ---------------------------------------------------------

    def mark_failure(
        self,
        provider_name: str,
    ) -> None:

        self.selector.report_failure(
            provider_name,
        )

    # ---------------------------------------------------------

    def provider_names(
        self,
    ) -> tuple[str, ...]:

        return self.registry.names()

    # ---------------------------------------------------------

    def provider_count(
        self,
    ) -> int:

        return len(self.registry)

    # ---------------------------------------------------------

    def has_provider(
        self,
        name: str,
    ) -> bool:

        return self.registry.exists(name)

    # ---------------------------------------------------------

    def get(
        self,
        name: str,
    ) -> BaseLLMProvider:

        return self.registry.get(name).provider

    # ---------------------------------------------------------

    def by_model(
        self,
        model: str,
    ) -> BaseLLMProvider:

        model = model.lower()

        if "gemini" in model:

            return self.get("Gemini")

        if "groq" in model:

            return self.get("Groq")

        if (
            "gpt" in model
            or "openrouter" in model
        ):

            return self.get("OpenRouter")

        if any(
            family in model
            for family in (
                "llama",
                "qwen",
                "mistral",
                "phi",
                "deepseek",
            )
        ):

            if self.has_provider("Ollama"):

                return self.get("Ollama")

            return self.get("Groq")

        return self.provider()

    # ---------------------------------------------------------

    @property
    def current_provider(
        self,
    ) -> BaseLLMProvider | None:

        return self.selector.current()