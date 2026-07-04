from __future__ import annotations

from pathlib import Path

from PIL import Image
from google import genai
from google.genai import types

from brain.llm.llm_request import LLMRequest
from brain.llm.provider_response import ProviderResponse

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.capabilities import ProviderCapability

from config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
)

from tools.schema import TOOLS
from logs.logger import logger


class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini provider.

    Responsibilities
    ----------------
    • Execute an LLMRequest
    • Return a ProviderResponse

    This class never performs routing, reasoning,
    prompt construction or conversation management.
    """

    @property
    def name(self) -> str:
        return "Gemini"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            name="Gemini",
            chat=True,
            vision=True,
            tools=True,
            streaming=True,
            reasoning_score=8,
            coding_score=8,
            speed_score=7,
            privacy_score=3,
            local=False,
            context_window=1_048_576,
            cost_score=4,
        )

    # ---------------------------------------------------------

    def __init__(self) -> None:
        logger.info("Initializing Gemini Provider...")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    # ---------------------------------------------------------

    def generate(
        self,
        request: LLMRequest,
    ) -> ProviderResponse:

        self._validate(request)

        config = self._config(request)

        try:

            if request.image is not None:
                contents = self._vision_contents(request)
            else:
                contents = [
                    request.system_prompt,
                    request.user_input,
                ]

            response = self.client.models.generate_content(
                model=request.model or GEMINI_MODEL,
                contents=contents,
                config=config,
            )

            return ProviderResponse(
                text=response.text or "",
                provider=self.name,
                raw=response,
            )

        except Exception:
            logger.exception("Gemini generation failed.")
            raise

    # ---------------------------------------------------------

    def _config(
        self,
        request: LLMRequest,
    ) -> types.GenerateContentConfig:

        return types.GenerateContentConfig(
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
            tools=TOOLS if getattr(request, "tools", False) else None,
        )

    # ---------------------------------------------------------

    def _vision_contents(
        self,
        request: LLMRequest,
    ) -> list:

        image_path = Path(request.image)

        if not image_path.exists():
            raise FileNotFoundError(image_path)

        with Image.open(image_path) as image:

            image.load()

            return [
                request.system_prompt,
                request.user_input,
                image.copy(),
            ]

    # ---------------------------------------------------------

    @staticmethod
    def _validate(
        request: LLMRequest,
    ) -> None:

        if not request.user_input.strip():
            raise ValueError("LLMRequest.user_input cannot be empty.")