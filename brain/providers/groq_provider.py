from groq import Groq

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.capabilities import ProviderCapability
from brain.models import ProviderResponse

from config.settings import (
    GROQ_API_KEY,
    GROQ_MODEL,
)

from logs.logger import logger


class GroqProvider(BaseLLMProvider):

    @property
    def name(self):

        return "Groq"

    # ---------------------------------------------------------

    @property
    def capability(self):

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

            cost_score=1

        )

    # ---------------------------------------------------------

    def __init__(self):

        logger.info(
            "Initializing Groq Provider..."
        )

        self.client = Groq(
            api_key=GROQ_API_KEY
        )

        self.model = GROQ_MODEL

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

            "Groq vision is not available."

        )

    # ---------------------------------------------------------

    def supports_tools(self):

        return True