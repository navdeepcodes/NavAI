from __future__ import annotations

import json
import logging

from brain.cognition.decision.decision_parser import (
    DecisionParser,
)
from brain.cognition.decision.decision_prompt import (
    DECISION_SYSTEM_PROMPT,
)
from brain.cognition.models.decision import Decision
from brain.cognition.models.understanding import Understanding
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    Mike's Decision Engine.

    Responsibilities
    ----------------
    • Decide Mike's next objective.
    • Decide whether planning is required.
    • Decide whether execution is required.
    • Decide whether clarification is required.

    This engine NEVER:
    • Generates user-facing responses.
    • Executes tools.
    • Modifies session state.
    """

    # =====================================================

    def __init__(
        self,
        llm: LLMService,
    ) -> None:

        self._llm = llm
        self._parser = DecisionParser()

    # =====================================================

    def decide(
        self,
        *,
        user_message: str,
        understanding: Understanding,
        context: str = "",
    ) -> Decision:

        logger.info("Making decision...")

        request = LLMRequest(

            system_prompt=DECISION_SYSTEM_PROMPT,

            user_input=self._build_prompt(
                user_message=user_message,
                understanding=understanding,
                context=context,
            ),

            metadata={
                "task": "decision",
            },

            temperature=0.0,

            max_tokens=500,

        )

        try:

            response = self._llm.run(
                request,
            )

            if not response.success:

                raise RuntimeError(
                    "Decision provider failed."
                )

            decision = self._parser.parse(
                response.text,
            )

        except Exception:

            logger.exception(
                "Decision engine failed."
            )

            decision = Decision(

                action="RESPOND",

                confidence=0.0,

                reasoning="Decision engine failure.",

                requires_response=True,

                requires_execution=False,

                requires_memory=False,

                requires_clarification=False,

                execution_goal=None,

                tool=None,

                tool_action=None,

                arguments={},

                planner_hint=None,

                memory_operation=None,

                metadata={},

            )

        logger.info(

            "Decision complete | action=%s | execution=%s | tool=%s | confidence=%.2f",

            decision.action,

            decision.requires_execution,

            decision.tool,

            decision.confidence,

        )

        return decision

    # =====================================================

    @staticmethod
    def _build_prompt(
        *,
        user_message: str,
        understanding: Understanding,
        context: str,
    ) -> str:

        context = context.strip() or "No previous conversation."

        understanding_payload = {

            "intent": understanding.intent,

            "goal": understanding.goal,

            "confidence": understanding.confidence,

            "requires_context": understanding.requires_context,

            "referenced_entities": understanding.referenced_entities,

            "referenced_messages": understanding.referenced_messages,

            "is_complete": understanding.is_complete,

            "missing_information": understanding.missing_information,

            "needs_clarification": understanding.needs_clarification,

            "clarification": understanding.clarification,

            "requires_memory": understanding.requires_memory,

            "memory_query": understanding.memory_query,

            "emotion": understanding.emotion,

            "tone": understanding.tone,

            "metadata": understanding.metadata,

        }

        return f"""
Conversation Context
====================

{context}

==================================================

Latest User Message

{user_message}

==================================================

Semantic Understanding

{json.dumps(understanding_payload, indent=2, ensure_ascii=False)}

==================================================

Your task is to decide Mike's NEXT OBJECTIVE.

Do NOT reinterpret the user's message.

Do NOT answer the user.

Do NOT generate natural language.

Do NOT plan execution.

Do NOT execute tools.

Base your decision ONLY on the semantic understanding above.

Determine:

• whether Mike should respond conversationally
• whether tools are required
• whether clarification is required
• whether memory is required
• whether planning is required
• which tool should be used (if any)
• the execution objective

Return ONLY valid JSON.
""".strip()