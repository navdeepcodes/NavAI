from __future__ import annotations

import logging
from datetime import datetime

from brain.intelligence.greeting_prompt import GREETING_SYSTEM_PROMPT
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class GreetingEngine:
    """
    Generates Mike's startup greeting.

    Runs once during startup.

    Future context sources
    ----------------------
    • User memory
    • Previous session
    • Active project
    • Current workspace
    """

    def __init__(self) -> None:

        self._llm = LLMService()

    # =====================================================

    def generate(self) -> str:

        logger.info("Generating startup greeting...")

        hour = datetime.now().hour

        if hour < 12:
            period = "morning"
        elif hour < 17:
            period = "afternoon"
        elif hour < 21:
            period = "evening"
        else:
            period = "night"

        user_prompt = f"""
Generate a startup greeting.

Current time period: {period}

Requirements:
- Maximum two short sentences.
- Professional.
- Friendly.
- No emojis.
- No markdown.
- No introductions like "Hello, I am Mike."
- Do not mention being an AI.
- Sound like a desktop assistant that is already running.
"""

        request = LLMRequest(
            system_prompt=GREETING_SYSTEM_PROMPT,
            user_input=user_prompt,
            metadata={
                "task": "startup_greeting",
                "period": period,
            },
        )

        try:

            response = self._llm.run(request)

            text = response.text.strip()

            if text:
                return text

        except Exception:
            logger.exception("Greeting generation failed.")

        return self._fallback(period)

    # =====================================================

    @staticmethod
    def _fallback(period: str) -> str:

        greetings = {
            "morning": "Good morning. Ready when you are.",
            "afternoon": "Good afternoon. What are we working on today?",
            "evening": "Good evening. Ready to continue?",
            "night": "You're back. Ready when you are.",
        }

        return greetings.get(period, "Ready.")