from __future__ import annotations

import logging

from brain.intelligence.thinking_engine import ThinkingEngine
from brain.llm.llm_service import LLMService
from brain.session.context_builder import ContextBuilder
from brain.session.session import Session

from brain.intelligence.mind import Mind

logger = logging.getLogger(__name__)


class IntelligenceEngine:
    """
    Mike's Cognitive Orchestrator.

    Responsibilities
    ----------------
    • Maintain session state
    • Build context
    • Run thinking layer
    • Produce Mind (intermediate cognition output)
    """

    # =====================================================

    def __init__(self) -> None:

        self.session = Session()
        self.context_builder = ContextBuilder()

        self.llm = LLMService()
        self.thinking = ThinkingEngine(self.llm)

    # =====================================================

    def think(self, message: str) -> Mind:

        logger.info("Starting cognitive pipeline...")

        # -------------------------------------------------
        # Store user input
        # -------------------------------------------------

        self.session.add_user(message)

        # -------------------------------------------------
        # Build context
        # -------------------------------------------------

        context = self.context_builder.build(
            session=self.session,
            user_message=message,
        )

        # -------------------------------------------------
        # Thinking layer (LLM)
        # -------------------------------------------------

        thinking = self.thinking.think(
            user_message=message,
            context=context,
        )

        logger.info(
            "Thinking complete | intent=%s | action=%s | confidence=%.2f",
            thinking.intent,
            thinking.action,
            thinking.confidence,
        )

        # -------------------------------------------------
        # Update session memory signals
        # -------------------------------------------------

        if thinking.goal:
            self.session.current_topic = thinking.goal

        if thinking.memory_query:
            self.session.metadata["memory_query"] = thinking.memory_query

        # -------------------------------------------------
        # Build Mind object
        # -------------------------------------------------

        mind = Mind(
            user_message=message,
            thinking=thinking,
            conversation_memory=self.session,
        )

        logger.info("Cognitive pipeline completed.")

        return mind

    # =====================================================

    def add_assistant_message(self, message: str) -> None:

        if not message:
            return

        self.session.add_assistant(message)

    # =====================================================

    def reset(self) -> None:

        logger.info("Resetting cognitive session.")

        self.session = Session()