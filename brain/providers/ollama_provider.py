from pathlib import Path

import ollama

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.capabilities import ProviderCapability
from brain.models import ProviderResponse

from config.ollama import (
    OLLAMA_HOST,
    OLLAMA_CHAT_MODEL,
    OLLAMA_VISION_MODEL,
)

from logs.logger import logger


class OllamaProvider(BaseLLMProvider):

    @property
    def name(self):

        return "Ollama"

    # ---------------------------------------------------------

    @property
    def capability(self):

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

            context_window=32768,

            cost_score=0

        )

    # ---------------------------------------------------------

    def __init__(self):

        logger.info(
            "Initializing Ollama Provider..."
        )

        self.client = ollama.Client(
            host=OLLAMA_HOST
        )

        self.chat_model = OLLAMA_CHAT_MODEL

        self.vision_model = OLLAMA_VISION_MODEL

    # ---------------------------------------------------------

    def _ensure_image(

        self,

        image

    ):

        if image is None:

            raise ValueError(
                "Image required."
            )

        image = Path(image)

        if not image.exists():

            raise FileNotFoundError(image)

        return image

    # ---------------------------------------------------------

    def _generate(

        self,

        prompt: str,

        **kwargs

    ) -> ProviderResponse:

        response = self.client.generate(

            model=self.chat_model,

            prompt=prompt,

            options={

                "temperature": kwargs.get("temperature")

            }

        )

        return ProviderResponse(

            text=response.response,

            provider=self.name,

            model=self.chat_model,

            finish_reason=response.done_reason,

            input_tokens=response.prompt_eval_count or 0,

            output_tokens=response.eval_count or 0,

            raw=response

        )

    # ---------------------------------------------------------

    def _generate_vision(

        self,

        prompt: str,

        image,

        **kwargs

    ) -> ProviderResponse:

        image = self._ensure_image(

            image

        )

        response = self.client.chat(

            model=self.vision_model,

            messages=[

                {

                    "role": "user",

                    "content": prompt,

                    "images": [

                        str(image)

                    ]

                }

            ]

        )

        return ProviderResponse(

            text=response.message.content,

            provider=self.name,

            model=self.vision_model,

            finish_reason=response.done_reason,

            raw=response

        )

    # ---------------------------------------------------------

    def _generate_stream(

        self,

        prompt: str,

        **kwargs

    ):

        stream = self.client.generate(

            model=self.chat_model,

            prompt=prompt,

            stream=True,

            options={

                "temperature": kwargs.get("temperature")

            }

        )

        for chunk in stream:

            if chunk.response:

                yield chunk.response

    # ---------------------------------------------------------

    def health_check(

        self

    ):

        try:

            self.client.list()

            return True

        except Exception as e:

            logger.warning(e)

            return False

    # ---------------------------------------------------------

    def supports_tools(self):

        return False