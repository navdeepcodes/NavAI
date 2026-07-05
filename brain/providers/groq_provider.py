from __future__ import annotations

from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    Groq,
)

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
    Groq Provider

    Responsibilities
    ----------------
    • Execute a request.
    • Return ProviderResponse.

    Never:
    • Retry
    • Sleep
    • Perform fallback
    • Handle routing
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
            context_window=131072,
            cost_score=1,
        )

    # ---------------------------------------------------------

    def __init__(self) -> None:

        logger.info("Initializing Groq Provider...")

        self.client = Groq(
            api_key=GROQ_API_KEY,
            max_retries=0,      # Disable SDK retries
            timeout=20.0,       # Fail fast
        )

    # ---------------------------------------------------------

    def generate(
        self,
        request: LLMRequest,
    ) -> ProviderResponse:

        if request.image is not None:
            raise NotImplementedError(
                "Groq does not support vision."
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
            )

            usage = response.usage

            return ProviderResponse(
                text=response.choices[0].message.content or "",
                provider=self.name,
                model=request.model or GROQ_MODEL,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                finish_reason=response.choices[0].finish_reason,
                raw=response,
            )

        except APIStatusError as e:

            logger.warning(
                "Groq HTTP %s: %s",
                e.status_code,
                e,
            )
            raise

        except APITimeoutError:

            logger.warning(
                "Groq request timed out."
            )
            raise

        except APIConnectionError:

            logger.warning(
                "Groq connection failed."
            )
            raise

        except Exception:

            logger.exception(
                "Groq generation failed."
            )
            raise

    # ---------------------------------------------------------

    def stream(
        self,
        request: LLMRequest,
    ):

        if request.image is not None:
            raise NotImplementedError(
                "Groq does not support vision."
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
            )

            for chunk in stream:

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta.content

                if delta:
                    yield delta

        except APIStatusError as e:

            logger.warning(
                "Groq HTTP %s: %s",
                e.status_code,
                e,
            )
            raise

        except APITimeoutError:

            logger.warning(
                "Groq stream timed out."
            )
            raise

        except APIConnectionError:

            logger.warning(
                "Groq connection failed."
            )
            raise

        except Exception:

            logger.exception(
                "Groq streaming failed."
            )
            raise

    # ---------------------------------------------------------

    def health_check(self) -> bool:

        return bool(GROQ_API_KEY)