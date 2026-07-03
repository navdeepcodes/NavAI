from abc import abstractmethod
from time import perf_counter

from brain.models import (
    Conversation,
    ProviderResponse,
)

from brain.prompt_builder import PromptBuilder

from brain.providers.base_provider import BaseProvider

from logs.logger import logger


class BaseLLMProvider(BaseProvider):

    HEALTH_CHECK_PROMPT = "Reply with OK."

    # ---------------------------------------------------------
    # Prompt Builder
    # ---------------------------------------------------------

    def build_prompt(
        self,
        conversation: Conversation
    ) -> str:

        return PromptBuilder(
            conversation
        ).build()

    # ---------------------------------------------------------
    # Hooks (override if needed)
    # ---------------------------------------------------------

    def before_request(
        self,
        prompt: str,
        **kwargs
    ):

        pass

    def after_response(
        self,
        response: ProviderResponse
    ):

        pass

    def on_error(
        self,
        exception: Exception
    ):

        logger.exception(exception)

    # ---------------------------------------------------------
    # Internal execution helper
    # ---------------------------------------------------------

    def _execute(
        self,
        fn,
        *args,
        **kwargs
    ) -> ProviderResponse:

        self.before_request(
            args[0] if args else "",
            **kwargs
        )

        start = perf_counter()

        try:

            response = fn(
                *args,
                **kwargs
            )

            response.latency_ms = (

                perf_counter() - start

            ) * 1000

            self.after_response(
                response
            )

            return response

        except Exception as e:

            self.on_error(
                e
            )

            raise

    # ---------------------------------------------------------
    # Chat
    # ---------------------------------------------------------

    def chat(
        self,
        conversation: Conversation,
        **kwargs
    ) -> ProviderResponse:

        logger.info(
            f"[{self.name}] Chat"
        )

        prompt = self.build_prompt(
            conversation
        )

        return self._execute(
            self._generate,
            prompt,
            **kwargs
        )

    # ---------------------------------------------------------
    # Completion
    # ---------------------------------------------------------

    def complete(
        self,
        prompt: str,
        **kwargs
    ) -> str:

        logger.info(
            f"[{self.name}] Complete"
        )

        response = self._execute(
            self._generate,
            prompt,
            **kwargs
        )

        return response.text

    # ---------------------------------------------------------
    # Vision
    # ---------------------------------------------------------

    def vision(
        self,
        prompt: str,
        image,
        **kwargs
    ) -> ProviderResponse:

        logger.info(
            f"[{self.name}] Vision"
        )

        return self._execute(
            self._generate_vision,
            prompt,
            image,
            **kwargs
        )

    # ---------------------------------------------------------
    # Streaming
    # ---------------------------------------------------------

    def stream(
        self,
        conversation: Conversation,
        **kwargs
    ):

        logger.info(
            f"[{self.name}] Stream"
        )

        prompt = self.build_prompt(
            conversation
        )

        return self._generate_stream(
            prompt,
            **kwargs
        )

    # ---------------------------------------------------------
    # Health Check
    # ---------------------------------------------------------

    def health_check(
        self
    ) -> bool:

        try:

            self.complete(
                self.HEALTH_CHECK_PROMPT
            )

            return True

        except Exception as e:

            logger.warning(
                f"{self.name} health check failed: {e}"
            )

            return False

    # ---------------------------------------------------------
    # Provider-specific implementations
    # ---------------------------------------------------------

    @abstractmethod
    def _generate(
        self,
        prompt: str,
        **kwargs
    ) -> ProviderResponse:
        pass

    # ---------------------------------------------------------

    @abstractmethod
    def _generate_stream(
        self,
        prompt: str,
        **kwargs
    ):
        pass

    # ---------------------------------------------------------

    @abstractmethod
    def _generate_vision(
        self,
        prompt: str,
        image,
        **kwargs
    ) -> ProviderResponse:
        pass