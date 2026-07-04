from __future__ import annotations

import logging

from brain.intelligence.emotion import EmotionDetector
from brain.intelligence.models import Understanding
from brain.intelligence.understanding_parser import UnderstandingParser
from brain.intelligence.understanding_prompt import (
    UNDERSTANDING_SYSTEM_PROMPT,
)
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService


logger = logging.getLogger(__name__)


class UnderstandingEngine:
    """
    Mike's semantic understanding engine.

    Responsibilities
    ----------------
    • Understand the user's request using an LLM
    • Convert the response into a structured Understanding object
    • Attach locally detected emotion
    • Never allow LLM failures to crash Mike
    """

    # ---------------------------------------------------------

    def __init__(self) -> None:

        self.llm = LLMService()

        self.parser = UnderstandingParser()

        self.emotion = EmotionDetector()

    # ---------------------------------------------------------

    def understand(
        self,
        message: str,
    ) -> Understanding:

        logger.info(
            "Understanding user request..."
        )

        detected_emotion = self.emotion.detect(
            message
        )

        request = LLMRequest(

            system_prompt=UNDERSTANDING_SYSTEM_PROMPT,

            user_input=self._build_prompt(
                message
            ),

            metadata={
                "task": "understanding",
            },

        )

        try:

            response = self.llm.run(
                request
            )

            understanding = self.parser.parse(
                response.text
            )

        except Exception:

            logger.exception(
                "Understanding failed."
            )

            understanding = self.parser._fallback()

        # ---------------------------------------------
        # Local emotion detection always wins
        # ---------------------------------------------

        understanding.emotional_tone = (
            detected_emotion.label
        )

        return understanding

    # ---------------------------------------------------------

    def _build_prompt(
        self,
        message: str,
    ) -> str:

        return f"""
Analyze the following user request.

Return ONLY valid JSON.

User Request:
{message}
"""