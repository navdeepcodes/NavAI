from logs.logger import logger

from brain.providers.gemini_provider import GeminiProvider
from brain.providers.openrouter_provider import OpenRouterProvider


class VisionAnalyzer:

    def __init__(self):

        self.provider = self._get_provider()

    # -----------------------------------------

    def _get_provider(self):

        # Try Gemini first
        try:

            provider = GeminiProvider()

            if provider.health_check():

                logger.info(
                    "Using Gemini Vision"
                )

                return provider

        except Exception as e:

            logger.warning(
                f"Gemini Vision unavailable: {e}"
            )

        # Fallback to OpenRouter
        try:

            provider = OpenRouterProvider()

            logger.info(
                "Using OpenRouter Vision"
            )

            return provider

        except Exception as e:

            logger.warning(
                f"OpenRouter Vision unavailable: {e}"
            )

        raise RuntimeError(
            "No vision provider available."
        )

    # -----------------------------------------

    def analyze(
        self,
        image_path: str,
        prompt: str = "Describe this image."
    ):

        logger.info(
            f"Analyzing image: {image_path}"
        )

        return self.provider.vision(
            prompt,
            image_path
        )