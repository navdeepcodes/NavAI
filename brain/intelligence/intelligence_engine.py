from __future__ import annotations

import logging

from brain.conversation.conversation_engine import ConversationEngine

from brain.intelligence.context import ContextManager
from brain.intelligence.decision import DecisionEngine
from brain.intelligence.mind import Mind

from brain.intelligence.models import (
    Confidence,
    Emotion,
)

from brain.intelligence.reasoning import ReasoningEngine
from brain.intelligence.understanding import UnderstandingEngine


logger = logging.getLogger(__name__)


class IntelligenceEngine:
    """
    Mike's Cognitive Orchestrator.

    Responsibilities
    ----------------
    • Coordinate every cognitive subsystem.
    • Maintain short-term context.
    • Construct the final Mind object.

    This class NEVER performs reasoning,
    decision making or conversation itself.

    Pipeline

        User Message
              ↓
          Context
              ↓
       Understanding
              ↓
         Reasoning
              ↓
      Conversation Style
              ↓
          Decision
              ↓
             Mind
    """

    # ---------------------------------------------------------

    def __init__(self):

        self.context = ContextManager()

        self.understanding = UnderstandingEngine()

        self.reasoning = ReasoningEngine()

        self.conversation = ConversationEngine()

        self.decision = DecisionEngine()

    # ---------------------------------------------------------

    def think(
        self,
        message: str,
    ) -> Mind:

        logger.info("Starting cognitive pipeline...")

        # -------------------------------------------------
        # Context
        # -------------------------------------------------

        self.context.add_message(message)

        context = self.context.current

        # -------------------------------------------------
        # Understanding
        # -------------------------------------------------

        understanding = self.understanding.understand(
            message
        )

        logger.info(

            "Understanding complete | goal=%s | intent=%s | confidence=%.2f",

            understanding.goal,

            understanding.intent,

            understanding.confidence,

        )

        # -------------------------------------------------
        # Reasoning
        # -------------------------------------------------

        reasoning = self.reasoning.reason(

            understanding,

            context,

        )

        logger.info("Reasoning complete.")

        # -------------------------------------------------
        # Conversation Intelligence
        # -------------------------------------------------

        conversation = self.conversation.analyze(

            user_message=message,

            understanding=understanding,

            reasoning=reasoning,

            context=context,

        )

        logger.info(

            "Conversation complete | tone=%s",

            conversation.tone,

        )

        # -------------------------------------------------
        # Executive Decision
        # -------------------------------------------------

        decision = self.decision.decide(

            user_message=message,

            understanding=understanding,

            reasoning=reasoning,

            context=context,

        )

        logger.info(

            "Decision complete | action=%s",

            decision.action.name,

        )

        # -------------------------------------------------
        # Confidence
        # -------------------------------------------------

        confidence = Confidence(

            score=understanding.confidence,

            explanation="Derived from semantic understanding.",

        )

        # -------------------------------------------------
        # Emotion
        # -------------------------------------------------

        emotion = Emotion(

            label=understanding.emotional_tone,

            confidence=understanding.confidence,

        )

        # -------------------------------------------------
        # Construct Mind
        # -------------------------------------------------

        mind = Mind(

            user_message=message,

            understanding=understanding,

            reasoning=reasoning,

            conversation=conversation,

            decision=decision,

            context=context,

            emotion=emotion,

            confidence=confidence,

        )

        logger.info("Cognitive pipeline completed.")

        return mind

    # ---------------------------------------------------------

    def reset(self) -> None:
        """
        Reset Mike's short-term conversational state.
        """

        logger.info("Resetting cognitive state.")

        self.context.reset()