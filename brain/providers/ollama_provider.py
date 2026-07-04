from __future__ import annotations

from pathlib import Path

import ollama

from brain.llm.llm_request import LLMRequest
from brain.llm.provider_response import ProviderResponse

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.capabilities import ProviderCapability

from config.ollama import (
    OLLAMA_HOST,
    OLLAMA_CHAT_MODEL,
    OLLAMA_VISION_MODEL,
)

from logs.logger import logger


class OllamaProvider(BaseLLMProvider):
    """
    Ollama local LLM provider.

    Responsibilities
    ----------------
    • Execute an LLMRequest
    • Return a ProviderResponse

    Never performs routing, reasoning,
    or prompt construction.
    """

    @property
    def name(self) -> str:
        return "Ollama"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            name="Ollama",
            chat=True,
            vision=True,
            tools=False,
            streaming=True,
            reasoning_score=8,
            coding_score=8,
            speed_score=6,
            privacy_score=10,
            local=True,
            context_window=32_768,
            cost_score=0,
        )

    # ---------------------------------------------------------

    def __init__(self) -> None:
        logger.info("Initializing Ollama Provider...")

        self.client = ollama.Client(
            host=OLLAMA_HOST
        )

    # ---------------------------------------------------------

    def generate(
        self,
        request: LLMRequest,
    ) -> ProviderResponse:

        try:

            if request.image is not None:
                return self._vision(request)

            response = self.client.generate(
                model=request.model or OLLAMA_CHAT_MODEL,
                prompt=f"{request.system_prompt}\n\n{request.user_input}",
                options={
                    "temperature": request.temperature,
                    "num_predict": request.max_tokens,
                    "top_p": request.top_p,
                },
            )

            return ProviderResponse(
                text=response.response or "",
                provider=self.name,
                model=request.model or OLLAMA_CHAT_MODEL,
                finish_reason=response.done_reason,
                input_tokens=response.prompt_eval_count or 0,
                output_tokens=response.eval_count or 0,
                raw=response,
            )

        except Exception:
            logger.exception("Ollama generation failed.")
            raise

    # ---------------------------------------------------------

    def _vision(
        self,
        request: LLMRequest,
    ) -> ProviderResponse:

        image = self._validate_image(request.image)

        response = self.client.chat(
            model=request.model or OLLAMA_VISION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": request.system_prompt,
                },
                {
                    "role": "user",
                    "content": request.user_input,
                    "images": [str(image)],
                },
            ],
            options={
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "top_p": request.top_p,
            },
        )

        return ProviderResponse(
            text=response.message.content or "",
            provider=self.name,
            model=request.model or OLLAMA_VISION_MODEL,
            finish_reason=response.done_reason,
            raw=response,
        )

    # ---------------------------------------------------------

    def stream(
        self,
        request: LLMRequest,
    ):

        if request.image is not None:
            raise NotImplementedError(
                "Streaming vision is not supported."
            )

        try:

            stream = self.client.generate(
                model=request.model or OLLAMA_CHAT_MODEL,
                prompt=f"{request.system_prompt}\n\n{request.user_input}",
                stream=True,
                options={
                    "temperature": request.temperature,
                    "num_predict": request.max_tokens,
                    "top_p": request.top_p,
                },
            )

            for chunk in stream:

                text = chunk.response

                if text:
                    yield text

        except Exception:
            logger.exception("Ollama streaming failed.")
            raise

    # ---------------------------------------------------------

    @staticmethod
    def _validate_image(
        image: str | None,
    ) -> Path:

        if image is None:
            raise ValueError("Image is required.")

        path = Path(image)

        if not path.exists():
            raise FileNotFoundError(path)

        return path

    # ---------------------------------------------------------

    def health_check(self) -> bool:

        try:
            self.client.list()
            return True

        except Exception:
            logger.exception("Ollama health check failed.")
            return False