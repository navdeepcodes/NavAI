from __future__ import annotations

import time

from logs.logger import logger

from brain.provider import manager
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_response import LLMResponse
from brain.llm.metrics import MetricsCollector
from brain.llm.router import ProviderRouter


class LLMService:
    """
    Central entry point for all LLM requests.

    Responsibilities
    ----------------
    • Execute LLM requests
    • Parse structured responses
    • Record metrics
    • Notify ProviderManager of success/failure

    Never
    -----
    • Build prompts
    • Perform routing logic
    • Manage provider state
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

        last_error: Exception | None = None

        # ---------------------------------------------
        # Maximum two attempts:
        #
        # Current provider
        # One retry after failover
        # ---------------------------------------------

        for attempt in range(2):

            provider = self.router.provider(

                task=task,

                model=request.model,

            )

            logger.info(

                "Using provider: %s",

                provider.name,

            )

            start = time.perf_counter()

            try:

                response = provider.generate(
                    request
                )

                latency = (

                    time.perf_counter()

                    - start

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

                    model=response.model or provider.name,

                    latency_ms=latency,

                    metadata={

                        "provider": response.provider,

                        "finish_reason": response.finish_reason,

                        "tool_calls": response.tool_calls,

                    },

                )

            except Exception as e:

                latency = (

                    time.perf_counter()

                    - start

                ) * 1000

                last_error = e

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

                logger.exception(e)

                # Retry once with newly selected provider

                continue

        logger.error(

            "LLM request failed on all attempts."

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

    def metrics_snapshot(
        self,
    ) -> dict:

        return self.metrics.snapshot()