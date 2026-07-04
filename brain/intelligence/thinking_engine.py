from __future__ import annotations

import json
import logging
import re
from typing import Any

from brain.intelligence.thinking_prompt import (
    THINKING_SYSTEM_PROMPT,
)
from brain.intelligence.thinking_result import (
    ThinkingResult,
)
from brain.llm.llm_request import LLMRequest
from brain.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class ThinkingEngine:
    """
    Mike's Cognitive Engine.

    Responsibilities
    ----------------
    • Understand the user's request.
    • Produce one ThinkingResult.
    • Never execute tools.
    • Never perform planning.
    • Never generate the final response.
    """

    # =====================================================

    def __init__(self) -> None:

        self._llm = LLMService()

    # =====================================================

    def think(
        self,
        user_message: str,
        context: str = "",
    ) -> ThinkingResult:

        logger.info("Thinking...")

        request = LLMRequest(

            system_prompt=THINKING_SYSTEM_PROMPT,

            user_input=self._build_prompt(
                user_message=user_message,
                context=context,
            ),

            metadata={
                "task": "thinking",
            },

        )

        response = self._llm.run(request)

        return self._parse(response.text)

    # =====================================================

    @staticmethod
    def _build_prompt(
        *,
        user_message: str,
        context: str,
    ) -> str:

        return f"""
Context
-------
{context}

User
----
{user_message}

Return ONLY valid JSON.
""".strip()

    # =====================================================

    @staticmethod
    def _extract_json(
        text: str,
    ) -> str:

        text = text.strip()

        if text.startswith("```"):

            text = re.sub(
                r"^```(?:json)?",
                "",
                text,
                flags=re.IGNORECASE,
            )

            text = re.sub(
                r"```$",
                "",
                text,
            ).strip()

        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1:

            return text[start:end + 1]

        return text

    # =====================================================

    @staticmethod
    def _confidence(
        value: object,
    ) -> float:

        try:

            value = float(value)

        except Exception:

            return 0.0

        return max(
            0.0,
            min(
                value,
                1.0,
            ),
        )

    # =====================================================

    @staticmethod
    def _dict(
        value: Any,
    ) -> dict[str, Any]:

        if isinstance(value, dict):

            return value

        return {}

    # =====================================================

    def _parse(
        self,
        raw: str,
    ) -> ThinkingResult:

        try:

            payload = json.loads(
                self._extract_json(raw)
            )

            result = ThinkingResult(

                # -----------------------------------------
                # Understanding
                # -----------------------------------------

                intent=str(
                    payload.get(
                        "intent",
                        "UNKNOWN",
                    )
                ),

                goal=str(
                    payload.get(
                        "goal",
                        "",
                    )
                ),

                confidence=self._confidence(
                    payload.get(
                        "confidence",
                        0.0,
                    )
                ),

                emotion=str(
                    payload.get(
                        "emotion",
                        "neutral",
                    )
                ),

                tone=str(
                    payload.get(
                        "tone",
                        "neutral",
                    )
                ),

                # -----------------------------------------
                # Executive Decision
                # -----------------------------------------

                action=str(
                    payload.get(
                        "action",
                        "RESPOND",
                    )
                ),

                requires_tools=bool(
                    payload.get(
                        "requires_tools",
                        False,
                    )
                ),

                # -----------------------------------------
                # Tool Execution
                # -----------------------------------------

                tool=payload.get(
                    "tool",
                ),

                tool_action=payload.get(
                    "tool_action",
                ),

                arguments=self._dict(
                    payload.get(
                        "arguments",
                        {},
                    )
                ),

                execution_type=str(
                    payload.get(
                        "execution_type",
                        "single",
                    )
                ),

                # -----------------------------------------
                # Draft Response
                # -----------------------------------------

                response=str(
                    payload.get(
                        "response",
                        "",
                    )
                ),

                # -----------------------------------------
                # Optional Outputs
                # -----------------------------------------

                clarification=payload.get(
                    "clarification",
                ),

                planner_hint=payload.get(
                    "planner_hint",
                ),

                memory_query=payload.get(
                    "memory_query",
                ),

                metadata=self._dict(
                    payload.get(
                        "metadata",
                        {},
                    )
                ),

            )

            logger.info(
                "Thinking complete | intent=%s | action=%s | tool=%s | tool_action=%s | confidence=%.2f",
                result.intent,
                result.action,
                result.tool,
                result.tool_action,
                result.confidence,
            )

            return result

        except Exception:

            logger.exception(
                "Failed to parse ThinkingResult."
            )

            return ThinkingResult(

                intent="UNKNOWN",

                goal="",

                confidence=0.0,

                emotion="neutral",

                tone="neutral",

                action="CLARIFY",

                requires_tools=False,

                tool=None,

                tool_action=None,

                arguments={},

                execution_type="single",

                response="",

                clarification="Could you rephrase your request?",

                planner_hint=None,

                memory_query=None,

                metadata={},

            )