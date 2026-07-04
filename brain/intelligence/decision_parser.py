from __future__ import annotations

import json
import logging

from brain.intelligence.enums import DecisionAction
from brain.intelligence.models import Decision


logger = logging.getLogger(__name__)


class DecisionParser:
    """
    Converts raw LLM output into a validated Decision.

    Responsibilities
    ----------------
    • Parse LLM JSON output.
    • Validate the selected action.
    • Apply safe defaults.
    • Never allow malformed LLM output to crash Mike.
    """

    # ---------------------------------------------------------

    def parse(
        self,
        raw: str,
    ) -> Decision:

        try:

            data = self._extract_json(raw)

            action = self._parse_action(
                data.get("action", "RESPOND")
            )

            confidence = self._parse_confidence(
                data.get("confidence", 0.50)
            )

            reasoning = str(
                data.get("reason", "")
            ).strip()

            clarification_question = str(
                data.get(
                    "clarification_question",
                    "",
                )
            ).strip()

            return Decision(

                action=action,

                confidence=confidence,

                reasoning=reasoning,

                clarification_question=(
                    clarification_question or None
                ),

                requires_planning=(
                    action == DecisionAction.PLAN
                ),

                requires_memory=(
                    action == DecisionAction.MEMORY
                ),

                requires_clarification=(
                    action == DecisionAction.CLARIFY
                ),

            )

        except Exception:

            logger.exception(
                "Failed to parse Decision JSON."
            )

            return self.fallback()

    # ---------------------------------------------------------

    def fallback(
        self,
    ) -> Decision:
        """
        Safe fallback.

        If the Decision LLM fails for any reason,
        Mike defaults to a conversational response
        rather than executing actions.
        """

        return Decision(

            action=DecisionAction.RESPOND,

            confidence=0.25,

            reasoning="Decision parser fallback.",

            clarification_question=None,

            requires_planning=False,

            requires_memory=False,

            requires_clarification=False,

        )

    # ---------------------------------------------------------

    def _extract_json(
        self,
        raw: str,
    ) -> dict:

        raw = raw.strip()

        if raw.startswith("```"):

            raw = raw.split("\n", 1)[1]

            raw = raw.rsplit("```", 1)[0]

        return json.loads(raw)

    # ---------------------------------------------------------

    def _parse_action(
        self,
        value: str,
    ) -> DecisionAction:

        value = str(value).strip().upper()

        mapping = {

            "RESPOND": DecisionAction.RESPOND,

            "PLAN": DecisionAction.PLAN,

            "MEMORY": DecisionAction.MEMORY,

            "CLARIFY": DecisionAction.CLARIFY,

        }

        return mapping.get(
            value,
            DecisionAction.RESPOND,
        )

    # ---------------------------------------------------------

    def _parse_confidence(
        self,
        value,
    ) -> float:

        try:

            score = float(value)

        except Exception:

            score = 0.50

        return max(
            0.0,
            min(
                1.0,
                score,
            ),
        )