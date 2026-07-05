from __future__ import annotations

import logging

from brain.cognition.models.understanding import Understanding
from brain.cognition.understanding.understanding_parser import (
    UnderstandingParser,
)
from brain.cognition.understanding.understanding_prompt import (
    UNDERSTANDING_SYSTEM_PROMPT,
)
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class UnderstandingEngine:
    """
    Produces a semantic understanding of the user's request.

    This engine NEVER:
        • decides actions
        • chooses tools
        • plans execution
        • generates responses
    """

    # =====================================================

    def __init__(
        self,
        llm: LLMService,
    ) -> None:

        self._llm = llm
        self._parser = UnderstandingParser()

    # =====================================================

    def understand(
        self,
        *,
        user_message: str,
        context: str = "",
    ) -> Understanding:

        logger.info("Understanding user request...")

        request = LLMRequest(

            system_prompt=UNDERSTANDING_SYSTEM_PROMPT,

            user_input=self._build_prompt(
                user_message=user_message,
                context=context,
            ),

            metadata={
                "task": "understanding",
            },

            temperature=0.0,

            max_tokens=350,

        )

        response = self._llm.run(request)

        if not response.success:

            logger.error(
                "Understanding provider failed."
            )

            return Understanding(

                intent="UNKNOWN",

                goal=user_message,

                confidence=0.0,

                is_complete=False,

                clarification="Could you rephrase that?",

            )

        # =====================================================
        # DEBUG
        # =====================================================

        logger.info(
            "RAW UNDERSTANDING RESPONSE:\n%s",
            response.text,
        )

        # =====================================================

        understanding = self._parser.parse(
            response.text,
        )

        logger.info(
            "Parsed Understanding | intent=%s | goal=%s | confidence=%.2f",
            understanding.intent,
            understanding.goal,
            understanding.confidence,
        )

        return understanding

    # =====================================================

    @staticmethod
    def _build_prompt(
        *,
        user_message: str,
        context: str,
    ) -> str:

        context = context.strip() or "No previous conversation."

        return f"""
You are performing semantic understanding only.

Conversation Context
====================

{context}

====================

Latest User Message

{user_message}

Your task:

- Infer the user's intent.
- Infer the user's goal.
- Use the conversation context.
- Resolve references.
- Do NOT answer the user.
- Do NOT greet the user.
- Do NOT explain anything.
- Output ONLY the required JSON object.
""".strip()