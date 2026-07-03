from logs.logger import logger

from brain.providers.task_type import TaskType
from brain.providers.provider_request import ProviderRequest
from brain.providers.orchestrator import AIOrchestrator

from brain.providers.gemini_provider import GeminiProvider
from brain.providers.groq_provider import GroqProvider
from brain.providers.ollama_provider import OllamaProvider
from brain.providers.openrouter_provider import OpenRouterProvider


class ProviderManager:

    # ---------------------------------------------------------

    def __init__(self):

        logger.info(
            "Initializing Provider Manager..."
        )

        self.providers = []

        self._discover_providers()

        self.orchestrator = AIOrchestrator(
            self.providers
        )

    # ---------------------------------------------------------

    def _discover_providers(self):

        candidates = [

            GeminiProvider(),

            GroqProvider(),

            OllamaProvider(),

            OpenRouterProvider()

        ]

        for provider in candidates:

            logger.info(
                f"Checking {provider.name}..."
            )

            try:

                if provider.health_check():

                    logger.info(
                        f"{provider.name} available."
                    )

                    self.providers.append(
                        provider
                    )

                else:

                    logger.warning(
                        f"{provider.name} unavailable."
                    )

            except Exception as e:

                logger.exception(e)

        if not self.providers:

            raise RuntimeError(
                "No AI providers are available."
            )

    # ---------------------------------------------------------

    def reload(self):

        logger.info(
            "Reloading providers..."
        )

        self.providers.clear()

        self._discover_providers()

        self.orchestrator = AIOrchestrator(
            self.providers
        )

    # ---------------------------------------------------------

    def best_for(

        self,

        task: TaskType,

        **kwargs

    ):

        request = ProviderRequest(

            task=task,

            **kwargs

        )

        provider = self.orchestrator.choose(
            request
        )

        logger.info(
            f"Selected Provider -> {provider.name}"
        )

        return provider

    # ---------------------------------------------------------
    # Internal lightweight tasks
    # ---------------------------------------------------------

    def best_for_text(self):

        """
        Used for internal lightweight tasks
        such as intent detection.
        """

        priority = [

            "Groq",

            "Ollama",

            "OpenRouter",

            "Gemini"

        ]

        for name in priority:

            for provider in self.providers:

                if provider.name == name:

                    return provider

        if self.providers:

            return self.providers[0]

        raise RuntimeError(
            "No providers available."
        )

    # ---------------------------------------------------------

    def chat(

        self,

        conversation,

        **kwargs

    ):

        provider = self.best_for(

            TaskType.CHAT,

            **kwargs

        )

        return provider.chat(

            conversation,

            **kwargs

        )

    # ---------------------------------------------------------

    def reasoning(

        self,

        conversation,

        **kwargs

    ):

        provider = self.best_for(

            TaskType.REASONING,

            **kwargs

        )

        return provider.chat(

            conversation,

            **kwargs

        )

    # ---------------------------------------------------------

    def coding(

        self,

        conversation,

        **kwargs

    ):

        provider = self.best_for(

            TaskType.CODING,

            **kwargs

        )

        return provider.chat(

            conversation,

            **kwargs

        )

    # ---------------------------------------------------------

    def vision(

        self,

        prompt,

        image,

        **kwargs

    ):

        provider = self.best_for(

            TaskType.VISION,

            requires_vision=True,

            **kwargs

        )

        return provider.vision(

            prompt,

            image,

            **kwargs

        )

    # ---------------------------------------------------------

    def stream(

        self,

        conversation,

        **kwargs

    ):

        provider = self.best_for(

            TaskType.CHAT,

            streaming=True,

            **kwargs

        )

        return provider.stream(

            conversation,

            **kwargs

        )

    # ---------------------------------------------------------

    def available(self):

        return self.providers.copy()

    # ---------------------------------------------------------

    def provider_names(self):

        return [

            provider.name

            for provider in self.providers

        ]

    # ---------------------------------------------------------

    def get(

        self,

        name: str

    ):

        """
        Returns a provider by name.
        """

        for provider in self.providers:

            if provider.name.lower() == name.lower():

                return provider

        raise ValueError(

            f"Unknown provider: {name}"

        )

    # ---------------------------------------------------------

    def default(self):

        """
        Returns the first available provider.
        Mainly useful for debugging.
        """

        if not self.providers:

            raise RuntimeError(
                "No providers available."
            )

        return self.providers[0]