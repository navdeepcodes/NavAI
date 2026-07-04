from __future__ import annotations

import time

from logs.logger import logger

from brain.providers import manager
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_response import LLMResponse
from brain.llm.metrics import MetricsCollector
from brain.llm.router import ProviderRouter


class LLMService:
    """
    Central execution layer for every LLM request.

    Responsibilities
    ----------------
    • Execute requests
    • Iterate through routed providers
    • Record metrics
    • Update provider health

    Never
    -----
    • Build prompts
    • Select providers
    • Decide routing strategy
    """

    # =====================================================

    def __init__(self) -> None:

        self.router = ProviderRouter()

        self.metrics = MetricsCollector()

    # =====================================================

    def run(
        self,
        request: LLMRequest,
    ) -> LLMResponse:

        task = request.metadata.get(
            "task",
            "general",
        )

        providers = self.router.providers(
            task=task,
            model=request.model,
        )

        last_error: Exception | None = None

        for index, provider in enumerate(
            providers,
            start=1,
        ):

            logger.info(

                "Provider %s (%d/%d)",

                provider.name,

                index,

                len(providers),

            )

            start_time = time.perf_counter()

            try:

                response = provider.generate(
                    request
                )

                latency = (

                    time.perf_counter()

                    - start_time

                ) * 1000

                manager.mark_success(

                    provider.name,

                    latency,

                )

                parsed = None

                if (
                    request.parser is not None
                    and response.text
                ):

                    parsed = request.parser.parse(
                        response.text
                    )

                self.metrics.record(

                    task=task,

                    success=True,

                    latency_ms=latency,

                    prompt_tokens=response.input_tokens or 0,

                    completion_tokens=response.output_tokens or 0,

                )

                logger.info(

                    "Provider %s succeeded (%.1f ms)",

                    provider.name,

                    latency,

                )

                return LLMResponse(

                    success=True,

                    text=response.text,

                    parsed=parsed,

                    model=response.model
                    or provider.name,

                    latency_ms=latency,

                    metadata={

                        "provider": response.provider,

                        "finish_reason": response.finish_reason,

                        "tool_calls": response.tool_calls,

                    },

                )

            except Exception as exc:

                latency = (

                    time.perf_counter()

                    - start_time

                ) * 1000

                last_error = exc

                manager.mark_failure(
                    provider.name,
                )

                self.metrics.record(

                    task=task,

                    success=False,

                    latency_ms=latency,

                )

                logger.warning(

                    "Provider %s failed (%.1f ms)",

                    provider.name,

                    latency,

                )

                logger.exception(exc)

                if not self._retryable(exc):

                    break

        logger.error(
            "All providers failed."
        )

        return LLMResponse(

            success=False,

            text="",

            parsed=None,

            model=request.model,

            latency_ms=0.0,

            metadata={

                "error": str(last_error)

                if last_error
                else "Unknown provider failure.",

            },

        )

    # =====================================================

    @staticmethod
    def _retryable(
        error: Exception,
    ) -> bool:
        """
        Decide whether Mike should attempt another provider.

        This will evolve to classify provider-specific
        exceptions (timeouts, rate limits, auth errors, etc.).
        """

        return True

    # =====================================================

    def metrics_snapshot(
        self,
    ) -> dict:

        return self.metrics.snapshot()