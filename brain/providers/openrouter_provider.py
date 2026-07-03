from openai import OpenAI

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.capabilities import ProviderCapability
from brain.models import ProviderResponse

from config.settings import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
)

from logs.logger import logger


class OpenRouterProvider(BaseLLMProvider):

    @property
    def name(self):

        return "OpenRouter"

    # ---------------------------------------------------------

    @property
    def capability(self):

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

            context_window=200000,

            cost_score=5

        )

    # ---------------------------------------------------------

    def __init__(self):

        logger.info(
            "Initializing OpenRouter Provider..."
        )

        self.client = OpenAI(

            api_key=OPENROUTER_API_KEY,

            base_url="https://openrouter.ai/api/v1"

        )

        self.model = OPENROUTER_MODEL

    # ---------------------------------------------------------

    def _generate(

        self,

        prompt: str,

        **kwargs

    ) -> ProviderResponse:

        response = self.client.chat.completions.create(

            model=self.model,

            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            temperature=kwargs.get("temperature"),

            max_tokens=kwargs.get("max_tokens")

        )

        usage = getattr(

            response,

            "usage",

            None

        )

        return ProviderResponse(

            text=response.choices[0].message.content,

            provider=self.name,

            model=self.model,

            finish_reason=response.choices[0].finish_reason,

            input_tokens=getattr(
                usage,
                "prompt_tokens",
                0
            ) if usage else 0,

            output_tokens=getattr(
                usage,
                "completion_tokens",
                0
            ) if usage else 0,

            raw=response

        )

    # ---------------------------------------------------------

    def _generate_stream(

        self,

        prompt: str,

        **kwargs

    ):

        stream = self.client.chat.completions.create(

            model=self.model,

            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            stream=True,

            temperature=kwargs.get("temperature"),

            max_tokens=kwargs.get("max_tokens")

        )

        for chunk in stream:

            if (

                chunk.choices

                and

                chunk.choices[0].delta.content

            ):

                yield chunk.choices[0].delta.content

    # ---------------------------------------------------------

    def _generate_vision(

        self,

        prompt: str,

        image,

        **kwargs

    ):

        raise NotImplementedError(

            "Vision support will be implemented when using a vision-capable OpenRouter model."

        )

    # ---------------------------------------------------------

    def supports_tools(self):

        return True