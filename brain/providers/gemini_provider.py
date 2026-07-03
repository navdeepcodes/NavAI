from pathlib import Path

from PIL import Image

from google import genai
from google.genai import types

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.capabilities import ProviderCapability
from brain.models import ProviderResponse

from config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
)

from tools.schema import TOOLS

from logs.logger import logger


class GeminiProvider(BaseLLMProvider):

    @property
    def name(self):

        return "Gemini"

    # ---------------------------------------------------------

    @property
    def capability(self):

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

            cost_score=4

        )

    # ---------------------------------------------------------

    def __init__(self):

        logger.info(
            "Initializing Gemini Provider..."
        )

        self.client = genai.Client(
            api_key=GEMINI_API_KEY
        )

    # ---------------------------------------------------------

    def _config(self, **kwargs):

        return types.GenerateContentConfig(

            tools=TOOLS,

            temperature=kwargs.get("temperature"),

            max_output_tokens=kwargs.get("max_tokens")

        )

    # ---------------------------------------------------------

    def _generate(

        self,

        prompt: str,

        **kwargs

    ) -> ProviderResponse:

        response = self.client.models.generate_content(

            model=GEMINI_MODEL,

            contents=prompt,

            config=self._config(**kwargs)

        )

        return ProviderResponse(

            text=response.text,

            provider=self.name,

            raw=response

        )

    # ---------------------------------------------------------

    def _generate_vision(

        self,

        prompt: str,

        image,

        **kwargs

    ) -> ProviderResponse:

        image = Path(image)

        if not image.exists():

            raise FileNotFoundError(image)

        img = Image.open(image)

        response = self.client.models.generate_content(

            model=GEMINI_MODEL,

            contents=[

                prompt,

                img

            ],

            config=self._config(**kwargs)

        )

        return ProviderResponse(

            text=response.text,

            provider=self.name,

            raw=response

        )

    # ---------------------------------------------------------

    def _generate_stream(

        self,

        prompt: str,

        **kwargs

    ):

        stream = self.client.models.generate_content_stream(

            model=GEMINI_MODEL,

            contents=prompt,

            config=self._config(**kwargs)

        )

        for chunk in stream:

            if chunk.text:

                yield chunk.text

    # ---------------------------------------------------------

    def supports_tools(self):

        return True