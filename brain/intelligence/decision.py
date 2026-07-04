from __future__ import annotations

import logging

from brain.intelligence.decision_builder import DecisionPromptBuilder
from brain.intelligence.decision_parser import DecisionParser
from brain.intelligence.decision_prompt import DECISION_SYSTEM_PROMPT

from brain.intelligence.models import (
    Context,
    Decision,
    Reasoning,
    Understanding,
)

from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService


logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    Mike's Executive Decision Engine.

    Responsibilities
    ----------------
    • Decide Mike's next action.
    • Never generate user responses.
    • Never create execution plans.
    • Never execute tools.
    • Never contain business rules.

    This class is intentionally thin.

    Intelligence comes entirely from the LLM.

    Python is responsible only for orchestration,
    validation, logging and safe fallbacks.
    """

    # ---------------------------------------------------------

    def __init__(self):

        self.llm = LLMService()

        self.builder = DecisionPromptBuilder()

        self.parser = DecisionParser()

    # ---------------------------------------------------------

    def decide(
        self,
        *,
        user_message: str,
        understanding: Understanding,
        reasoning: Reasoning,
        context: Context,
    ) -> Decision:

        logger.info("Making executive decision...")

        try:

            prompt = self.builder.build(

                user_message=user_message,

                understanding=understanding,

                reasoning=reasoning,

                context=context,

            )

            response = self.llm.run(

                LLMRequest(

                    system_prompt=DECISION_SYSTEM_PROMPT,

                    user_input=prompt,

                    metadata={

                        "task": "decision",

                    },

                )

            )

            if response is None:

                raise RuntimeError(
                    "Decision LLM returned no response."
                )

            text = response.text.strip()

            if not text:

                raise RuntimeError(
                    "Decision LLM returned an empty response."
                )

            decision = self.parser.parse(text)

            logger.info(

                "Decision | action=%s | confidence=%.2f | reason=%s",

                decision.action.name,

                decision.confidence,

                getattr(decision, "reasoning", ""),

            )

            return decision

        except Exception:

            logger.exception(

                "Decision engine failed."

            )

            return self.parser.fallback()