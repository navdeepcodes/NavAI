from __future__ import annotations

import time

from logs.logger import logger

from brain.knowledge import knowledge
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_response import LLMResponse
from brain.llm.metrics import MetricsCollector
from brain.providers.provider_manager import ProviderManager


class LLMService:
    """
    Production LLM execution service.

    Responsibilities
    ----------------
    • Inject Mike's system knowledge.
    • Execute requests.
    • Automatically fail over between providers.
    • Report provider health.
    • Collect metrics.
    """

    # =====================================================

    def __init__(
        self,
        providers: ProviderManager | None = None,
    ) -> None:

        self.providers = providers or ProviderManager()
        self.metrics = MetricsCollector()

    # =====================================================

    def run(
        self,
        request: LLMRequest,
    ) -> LLMResponse:

        metadata = request.metadata or {}

        task = metadata.get(
            "task",
            "general",
        )

        # -------------------------------------------------

        system_prompt = f"""
{knowledge.system_context}

============================================================

{request.system_prompt}
""".strip()

        enriched_request = LLMRequest(

            system_prompt=system_prompt,

            user_input=request.user_input,

            parser=request.parser,

            metadata=request.metadata,

            model=request.model,

            temperature=request.temperature,

            max_tokens=request.max_tokens,

            timeout=request.timeout,

        )

        # -------------------------------------------------
        # Candidate providers
        # -------------------------------------------------

        if request.model:

            providers = [
                self.providers.by_model(
                    request.model,
                )
            ]

        else:

            providers = self.providers.providers(
                task,
            )

        if not providers:

            logger.error(
                "No providers available."
            )

            return LLMResponse(

                success=False,

                text="",

                parsed=None,

                model=request.model,

                latency_ms=0,

                metadata={
                    "provider": None,
                    "error": "No providers available.",
                },

            )

        # -------------------------------------------------

        overall_start = time.perf_counter()

        last_error: Exception | None = None

        # -------------------------------------------------
        # Try every provider
        # -------------------------------------------------

        for provider in providers:

            logger.info(
                "Trying provider '%s'.",
                provider.name,
            )

            provider_start = time.perf_counter()

            try:

                response = provider.generate(
                    enriched_request,
                )

                if response is None:

                    raise RuntimeError(
                        "Provider returned None."
                    )

                latency = (
                    time.perf_counter()
                    - provider_start
                ) * 1000

                self.providers.report_success(

                    provider.name,

                    latency,

                )

                parsed = None

                if (
                    enriched_request.parser
                    and response.text
                ):

                    try:

                        parsed = (
                            enriched_request.parser.parse(
                                response.text,
                            )
                        )

                    except Exception:

                        logger.exception(
                            "Parser failed."
                        )

                self.metrics.record(

                    task=task,

                    success=True,

                    latency_ms=latency,

                    prompt_tokens=response.input_tokens or 0,

                    completion_tokens=response.output_tokens or 0,

                )

                logger.info(

                    "Provider '%s' succeeded (%.1f ms).",

                    provider.name,

                    latency,

                )

                total_latency = (
                    time.perf_counter()
                    - overall_start
                ) * 1000

                return LLMResponse(

                    success=True,

                    text=response.text,

                    parsed=parsed,

                    model=response.model
                    or provider.name,

                    latency_ms=total_latency,

                    metadata={

                        "provider": provider.name,

                        "finish_reason": response.finish_reason,

                        "tool_calls": response.tool_calls,

                        "attempts": providers.index(provider)
                        + 1,

                    },

                )

            except Exception as exc:

                latency = (
                    time.perf_counter()
                    - provider_start
                ) * 1000

                last_error = exc

                self.providers.report_failure(
                    provider.name,
                )

                self.metrics.record(

                    task=task,

                    success=False,

                    latency_ms=latency,

                )

                logger.exception(

                    "Provider '%s' failed.",

                    provider.name,

                )

        # -------------------------------------------------
        # All providers failed
        # -------------------------------------------------

        total_latency = (
            time.perf_counter()
            - overall_start
        ) * 1000

        logger.error(
            "All providers failed."
        )

        return LLMResponse(

            success=False,

            text="",

            parsed=None,

            model=request.model,

            latency_ms=total_latency,

            metadata={

                "provider": None,

                "error": str(last_error)
                if last_error
                else "Unknown error",

                "attempted_providers": [
                    p.name
                    for p in providers
                ],

            },

        )

    # =====================================================

    def metrics_snapshot(
        self,
    ) -> dict:

        return self.metrics.snapshot()