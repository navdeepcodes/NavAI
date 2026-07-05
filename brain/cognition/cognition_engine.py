from __future__ import annotations

import logging

from brain.cognition.decision.decision_engine import DecisionEngine
from brain.cognition.models.cognition_state import CognitionState
from brain.cognition.models.decision import Decision
from brain.cognition.models.understanding import Understanding
from brain.cognition.understanding.understanding_engine import (
    UnderstandingEngine,
)
from brain.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class Cognition:
    """
    Mike's cognitive pipeline.

    Responsibilities
    ----------------
    • Build semantic understanding.
    • Decide what Mike should do.
    • Produce one CognitionState.

    Cognition never:

    • executes tools
    • generates responses
    • modifies the session
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

    # =====================================================

    def process(
        self,
        *,
        user_message: str,
        context: str = "",
    ) -> CognitionState:

        logger.info(
            "Starting cognition..."
        )

        # -------------------------------------------------
        # Understanding
        # -------------------------------------------------

        understanding: Understanding = (

            self._understanding.understand(

                user_message=user_message,

                context=context,

            )

        )

        # -------------------------------------------------
        # Decision
        # -------------------------------------------------

        decision: Decision = (

            self._decision.decide(

                user_message=user_message,

                understanding=understanding,

                context=context,

            )

        )

        # -------------------------------------------------
        # Cognition State
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