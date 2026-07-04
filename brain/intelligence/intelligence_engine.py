from __future__ import annotations

import logging

from brain.intelligence.context import ContextManager
from brain.intelligence.mind import Mind
from brain.intelligence.thinking_engine import ThinkingEngine

logger = logging.getLogger(__name__)


class IntelligenceEngine:
    """
    Mike's Cognitive Orchestrator.

    Responsibilities
    ----------------
    • Maintain conversational context.
    • Execute one cognitive reasoning pass.
    • Produce a Mind object.

    ThinkingEngine is the ONLY LLM-powered reasoning step.
    """

    # =====================================================

    def __init__(self) -> None:

        self.context = ContextManager()

        self.thinking = ThinkingEngine()

    # =====================================================

    def think(
        self,
        message: str,
    ) -> Mind:

        logger.info("Starting cognitive pipeline...")

        # -------------------------------------------------
        # Update Context
        # -------------------------------------------------

        self.context.add_message(message)

        context = self.context.current

        # -------------------------------------------------
        # Single Thinking Pass
        # -------------------------------------------------

        thinking = self.thinking.think(
            user_message=message,
            context=str(context),
        )

        logger.info(
            "Thinking complete | intent=%s | action=%s | confidence=%.2f",
            thinking.intent,
            thinking.action,
            thinking.confidence,
        )

        # -------------------------------------------------
        # Construct Mind
        # -------------------------------------------------

        mind = Mind(
            user_message=message,
            thinking=thinking,
        )

        logger.info("Cognitive pipeline completed.")

        return mind

    # =====================================================

    def reset(self) -> None:

        logger.info("Resetting cognitive context.")

        self.context.reset()