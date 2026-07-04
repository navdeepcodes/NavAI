from __future__ import annotations

import base64
from pathlib import Path

from openai import OpenAI

from brain.llm.llm_request import LLMRequest
from brain.llm.provider_response import ProviderResponse

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.capabilities import ProviderCapability

from config.settings import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
)

from logs.logger import logger


class OpenRouterProvider(BaseLLMProvider):
    """
    OpenRouter provider.

    Responsibilities
    ----------------
    • Execute an LLMRequest
    • Return a ProviderResponse

    Never performs routing, reasoning,
    or prompt construction.
    """

    @property
    def name(self) -> str:
        return "OpenRouter"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            name="OpenRouter",
            chat=True,
            vision=True,
            tools=True,
            streaming=True,
            reasoning_score=10,
            coding_score=10,
            speed_score=7,
            privacy_score=2,
            local=False,
            context_window=200_000,
            cost_score=5,
        )

    # ---------------------------------------------------------

    def __init__(self) -> None:

        logger.info("Initializing OpenRouter Provider...")

        self.client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )

    # ---------------------------------------------------------

    def generate(
        self,
        request: LLMRequest,
    ) -> ProviderResponse:

        try:

            messages = self._messages(request)

            response = self.client.chat.completions.create(
                model=request.model or OPENROUTER_MODEL,
                messages=messages,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens,
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
                model=request.model or OPENROUTER_MODEL,
                finish_reason=response.choices[0].finish_reason,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                raw=response,
            )

        except Exception:
            logger.exception("OpenRouter generation failed.")
            raise

    # ---------------------------------------------------------

    def stream(
        self,
        request: LLMRequest,
    ):

        try:

            messages = self._messages(request)

            stream = self.client.chat.completions.create(
                model=request.model or OPENROUTER_MODEL,
                messages=messages,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens,
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
            logger.exception("OpenRouter streaming failed.")
            raise

    # ---------------------------------------------------------

    def _messages(
        self,
        request: LLMRequest,
    ) -> list[dict]:

        messages = [
            {
                "role": "system",
                "content": request.system_prompt,
            }
        ]

        if request.image is None:

            messages.append(
                {
                    "role": "user",
                    "content": request.user_input,
                }
            )

            return messages

        image = self._encode_image(request.image)

        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": request.user_input,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image,
                        },
                    },
                ],
            }
        )

        return messages

    # ---------------------------------------------------------

    @staticmethod
    def _encode_image(
        image_path: str,
    ) -> str:

        path = Path(image_path)

        if not path.exists():
            raise FileNotFoundError(path)

        suffix = path.suffix.lower().replace(".", "")

        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()

        return f"data:image/{suffix};base64,{encoded}"