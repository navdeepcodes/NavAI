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
    Central façade for Mike's provider subsystem.

    Responsibilities
    ----------------
    • Discover providers
    • Register providers
    • Select providers
    • Report provider success/failure
    • Lookup providers

    Exactly one instance exists during Mike's lifetime.
    """

    _instance: ProviderManager | None = None

    # =====================================================

    def __new__(
        cls,
    ) -> ProviderManager:

        if cls._instance is None:

            cls._instance = super().__new__(cls)

            cls._instance._initialized = False

        return cls._instance

    # =====================================================

    def __init__(
        self,
    ) -> None:

        if self._initialized:
            return

        self._initialized = True

        logger.info(
            "Initializing Provider Manager..."
        )

        self.registry = ProviderRegistry()

        self.policy = ProviderPolicy(
            self.registry,
        )

        self.selector = ProviderSelector(
            self.registry,
        )

        self.reload()

    # =====================================================
    # Initialization
    # =====================================================

    def reload(
        self,
    ) -> None:

        self.registry.clear()

        self._discover()

        logger.info(
            "Provider Manager ready (%d providers).",
            len(self.registry),
        )

    # =====================================================

    def _candidate_providers(
        self,
    ) -> tuple[BaseLLMProvider, ...]:

        return (
            GroqProvider(),
            OllamaProvider(),
            OpenRouterProvider(),
            GeminiProvider(),
        )

    # =====================================================

    def _discover(
        self,
    ) -> None:

        for provider in self._candidate_providers():

            logger.info(
                "Checking provider '%s'...",
                provider.name,
            )

            try:

                if not provider.health_check():

                    logger.warning(
                        "Skipping '%s'.",
                        provider.name,
                    )

                    continue

                self.registry.register(
                    provider,
                )

            except Exception:

                logger.exception(
                    "Failed initializing '%s'.",
                    provider.name,
                )

        if len(self.registry) == 0:

            raise RuntimeError(
                "No providers are available."
            )

    # =====================================================
    # Selection
    # =====================================================

    def select(
        self,
        task: str = "general",
        model: str | None = None,
    ) -> BaseLLMProvider:

        if model:

            try:

                return self.by_model(
                    model,
                )

            except Exception:

                logger.warning(
                    "Requested model unavailable. Falling back."
                )

        candidates = self.policy.providers_for(
            task,
        )

        return self.selector.select(
            candidates,
        )

    # =====================================================

    def report_success(
        self,
        provider_name: str,
        latency_ms: float,
    ) -> None:

        self.selector.report_success(
            provider_name,
            latency_ms,
        )

    # =====================================================

    def report_failure(
        self,
        provider_name: str,
    ) -> None:

        self.selector.report_failure(
            provider_name,
        )

    # =====================================================
    # Lookup
    # =====================================================

    def providers(
        self,
        task: str = "general",
    ) -> list[BaseLLMProvider]:

        providers: list[
            BaseLLMProvider
        ] = []

        for name in self.policy.providers_for(
            task,
        ):

            state = self.registry.get(
                name,
            )

            if state is not None:

                providers.append(
                    state.provider,
                )

        return providers

    # =====================================================

    def provider_names(
        self,
    ) -> tuple[str, ...]:

        return self.registry.names()

    # =====================================================

    def provider_count(
        self,
    ) -> int:

        return len(
            self.registry,
        )

    # =====================================================

    def has_provider(
        self,
        name: str,
    ) -> bool:

        return self.registry.exists(
            name,
        )

    # =====================================================

    def get(
        self,
        name: str,
    ) -> BaseLLMProvider:

        state = self.registry.get(
            name,
        )

        if state is None:

            raise ValueError(
                f"Unknown provider '{name}'."
            )

        return state.provider

    # =====================================================

    def by_model(
        self,
        model: str,
    ) -> BaseLLMProvider:

        model = model.lower()

        if "gemini" in model:

            return self.get(
                "Gemini",
            )

        if "groq" in model:

            return self.get(
                "Groq",
            )

        if (
            "gpt" in model
            or "openrouter" in model
        ):

            return self.get(
                "OpenRouter",
            )

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

            if self.has_provider(
                "Ollama",
            ):

                return self.get(
                    "Ollama",
                )

            return self.get(
                "Groq",
            )

        return self.select()

    # =====================================================

    @property
    def current_provider(
        self,
    ) -> BaseLLMProvider | None:

        return self.selector.current()