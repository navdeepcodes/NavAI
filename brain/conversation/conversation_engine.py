from __future__ import annotations

import logging
import time

from brain.conversation.conversation_builder import ConversationPromptBuilder
from brain.conversation.conversation_models import ConversationState
from brain.conversation.conversation_parser import ConversationParser
from brain.conversation.conversation_prompt import (
    CONVERSATION_SYSTEM_PROMPT,
)

from brain.intelligence.models import (
    Context,
    Reasoning,
    Understanding,
)

from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class ConversationEngine:
    """
    Mike's Conversation Analysis Engine.

    Responsibilities
    ----------------
    • Decide HOW Mike should communicate.
    • Detect conversational style.
    • Detect follow-up questions.
    • Detect whether context should be carried forward.
    • Never generate responses.
    • Never make executive decisions.
    • Never execute tools.

    Intelligence lives inside the LLM.
    Python is responsible for orchestration,
    validation and safe fallbacks.
    """

    # ---------------------------------------------------------

    def __init__(self) -> None:

        self.llm = LLMService()

        self.builder = ConversationPromptBuilder()

        self.parser = ConversationParser()

    # ---------------------------------------------------------

    def analyze(
        self,
        *,
        user_message: str,
        understanding: Understanding,
        reasoning: Reasoning,
        context: Context,
    ) -> ConversationState:

        logger.info(
            "Analyzing conversational state..."
        )

        started = time.perf_counter()

        try:

            prompt = self.builder.build(

                user_message=user_message,

                understanding=understanding,

                reasoning=reasoning,

                context=context,

            )

            request = LLMRequest(

                system_prompt=CONVERSATION_SYSTEM_PROMPT,

                user_input=prompt,

                metadata={

                    "task": "conversation_analysis",

                },

            )

            response = self.llm.run(request)

            if response is None:

                raise RuntimeError(
                    "Conversation LLM returned None."
                )

            text = response.text.strip()

            if not text:

                raise RuntimeError(
                    "Conversation LLM returned empty output."
                )

            state = self.parser.parse(text)

            elapsed = (
                time.perf_counter() - started
            ) * 1000

            logger.info(

                "Conversation analysis complete | tone=%s | follow_up=%s | %.1f ms",

                getattr(state, "tone", "unknown"),

                getattr(state, "is_follow_up", False),

                elapsed,

            )

            return state

        except Exception:

            logger.exception(
                "Conversation analysis failed."
            )

            return self._fallback()

    # ---------------------------------------------------------

    def _fallback(
        self,
    ) -> ConversationState:
        """
        Safe conversational fallback.

        If conversation analysis fails,
        Mike should continue naturally
        rather than interrupting the user.
        """

        return ConversationState()