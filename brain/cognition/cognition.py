from __future__ import annotations

import logging

from brain.cognition.decision.decision_engine import DecisionEngine
from brain.cognition.models.cognition_state import CognitionState
from brain.cognition.models.decision import Decision
from brain.cognition.models.understanding import Understanding
from brain.cognition.normalization.action_normalizer import ActionNormalizer
from brain.cognition.understanding.understanding_engine import (
    UnderstandingEngine,
)
from brain.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class Cognition:
    """
    Mike's cognition pipeline.

    Responsibilities
    ----------------
    • Understand the user's request.
    • Decide what Mike should do.
    • Normalize LLM decisions.
    • Produce a CognitionState.

    Cognition never:
    • Executes tools
    • Generates responses
    • Modifies session state
    """

    # =====================================================

    def __init__(self) -> None:

        self._llm = LLMService()

        self._understanding = UnderstandingEngine(
            self._llm,
        )

        self._decision = DecisionEngine(
            self._llm,
        )

        self._normalizer = ActionNormalizer()

    # =====================================================

    def process(
        self,
        *,
        user_message: str,
        context: str = "",
    ) -> CognitionState:

        logger.info("Starting cognition...")

        # -------------------------------------------------
        # Understanding
        # -------------------------------------------------

        understanding: Understanding = self._understanding.understand(
            user_message=user_message,
            context=context,
        )

        logger.info(
            "Understanding complete | intent=%s | confidence=%.2f",
            understanding.intent,
            understanding.confidence,
        )

        # -------------------------------------------------
        # Decision
        # -------------------------------------------------

        decision: Decision = self._decision.decide(
            user_message=user_message,
            understanding=understanding,
            context=context,
        )

        # -------------------------------------------------
        # Normalize Decision
        # -------------------------------------------------

        decision = self._normalizer.normalize(decision)

        logger.info(
            "Decision complete | action=%s | tool=%s | tool_action=%s",
            decision.action,
            decision.tool,
            decision.tool_action,
        )

        # -------------------------------------------------
        # Build cognition state
        # -------------------------------------------------

        state = CognitionState(

            user_message=user_message,

            raw_context=context,

            goal=understanding.goal,

            intent=understanding.intent,

            confidence=understanding.confidence,

            emotion=understanding.emotion,

            action=decision.action,

            requires_tools=decision.requires_execution,

            tool=decision.tool,

            tool_action=decision.tool_action,

            arguments=decision.arguments,

            metadata={
                "understanding": understanding,
                "decision": decision,
            },

        )

        logger.info(
            "Cognition completed | intent=%s | action=%s",
            state.intent,
            state.action,
        )

        return state