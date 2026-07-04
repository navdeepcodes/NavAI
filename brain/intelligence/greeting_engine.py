from __future__ import annotations

import logging

from brain.intelligence.greeting_prompt import GREETING_SYSTEM_PROMPT
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class GreetingEngine:
    """
    Generates Mike's startup greeting.

    This runs only once when Mike starts.

    It is intentionally isolated from the normal
    conversation pipeline.
    """

    def __init__(self) -> None:

        self.llm = LLMService()

    # ---------------------------------------------------------

    def generate(self) -> str:

        logger.info("Generating startup greeting...")

        request = LLMRequest(

            system_prompt=GREETING_SYSTEM_PROMPT,

            user_input="Generate today's greeting.",

            metadata={
                "task": "startup_greeting",
            },

        )

        try:

            response = self.llm.run(request)

            text = response.text.strip()

            if text:

                return text

        except Exception:

            logger.exception(
                "Greeting generation failed."
            )

        return "Hello."