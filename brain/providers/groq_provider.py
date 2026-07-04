from __future__ import annotations

from groq import Groq

from brain.llm.llm_request import LLMRequest
from brain.llm.provider_response import ProviderResponse

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.capabilities import ProviderCapability

from config.settings import (
    GROQ_API_KEY,
    GROQ_MODEL,
)

from logs.logger import logger


class GroqProvider(BaseLLMProvider):
    """
    Groq LLM provider.

    Responsibilities
    ----------------
    • Execute an LLMRequest
    • Return a ProviderResponse

    This provider does not perform routing,
    reasoning or prompt construction.
    """

    @property
    def name(self) -> str:
        return "Groq"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            name="Groq",
            chat=True,
            vision=False,
            tools=True,
            streaming=True,
            reasoning_score=7,
            coding_score=9,
            speed_score=10,
            privacy_score=2,
            local=False,
            context_window=131_072,
            cost_score=1,
        )

    # ---------------------------------------------------------

    def __init__(self) -> None:
        logger.info("Initializing Groq Provider...")
        self.client = Groq(api_key=GROQ_API_KEY)

    # ---------------------------------------------------------

    def generate(
        self,
        request: LLMRequest,
    ) -> ProviderResponse:

        if request.image is not None:
            raise NotImplementedError(
                "Groq does not support vision requests."
            )

        try:

            response = self.client.chat.completions.create(
                model=request.model or GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": request.system_prompt,
                    },
                    {
                        "role": "user",
                        "content": request.user_input,
                    },
                ],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                stop=list(request.stop_sequences)
                if request.stop_sequences
                else None,
                stream=False,
                timeout=request.timeout,
            )

            usage = response.usage

            return ProviderResponse(
                text=response.choices[0].message.content or "",
                provider=self.name,
                model=request.model or GROQ_MODEL,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                raw=response,
            )

        except Exception:
            logger.exception("Groq generation failed.")
            raise

    # ---------------------------------------------------------

    def stream(
        self,
        request: LLMRequest,
    ):
        """
        Streaming generator.

        Returns plain text chunks.
        """

        if request.image is not None:
            raise NotImplementedError(
                "Groq does not support vision requests."
            )

        try:

            stream = self.client.chat.completions.create(
                model=request.model or GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": request.system_prompt,
                    },
                    {
                        "role": "user",
                        "content": request.user_input,
                    },
                ],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
                stop=list(request.stop_sequences)
                if request.stop_sequences
                else None,
                stream=True,
                timeout=request.timeout,
            )

            for chunk in stream:

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta.content

                if delta:
                    yield delta

        except Exception:
            logger.exception("Groq streaming failed.")
            raise