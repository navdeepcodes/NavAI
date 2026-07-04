from __future__ import annotations

import json
import logging

from brain.intelligence.models import Understanding
from brain.intelligence.enums import EmotionLabel


logger = logging.getLogger(__name__)


class UnderstandingParser:
    """
    Parses raw LLM JSON into a validated Understanding object.

    The parser NEVER invents information.
    It only validates and converts the LLM output into the
    Understanding model used throughout Mike.
    """

    # ---------------------------------------------------------

    def parse(
        self,
        raw: str,
    ) -> Understanding:

        try:

            data = self._extract_json(raw)

            emotion = self._emotion(
                data.get(
                    "emotional_tone",
                    "NEUTRAL",
                )
            )

            return Understanding(

                goal=str(
                    data.get(
                        "goal",
                        "conversation",
                    )
                ),

                intent=str(
                    data.get(
                        "intent",
                        "conversation",
                    )
                ),

                requires_tools=bool(
                    data.get(
                        "requires_tools",
                        False,
                    )
                ),

                entities=self._dict(
                    data.get(
                        "entities",
                        {},
                    )
                ),

                constraints=self._dict(
                    data.get(
                        "constraints",
                        {},
                    )
                ),

                confidence=self._confidence(
                    data.get(
                        "confidence",
                        0.5,
                    )
                ),

                emotional_tone=emotion,

            )

        except Exception:

            logger.exception(
                "Failed to parse Understanding."
            )

            return self._fallback()

    # ---------------------------------------------------------

    def _extract_json(
        self,
        raw: str,
    ) -> dict:

        raw = raw.strip()

        # Remove markdown code fences

        if raw.startswith("```"):

            raw = raw.split("\n", 1)[1]

            raw = raw.rsplit("```", 1)[0]

        # Extract first JSON object if the LLM adds text

        start = raw.find("{")
        end = raw.rfind("}")

        if start != -1 and end != -1:

            raw = raw[start:end + 1]

        return json.loads(raw)

    # ---------------------------------------------------------

    def _confidence(
        self,
        value,
    ) -> float:

        try:

            value = float(value)

        except Exception:

            value = 0.5

        return max(
            0.0,
            min(
                1.0,
                value,
            ),
        )

    # ---------------------------------------------------------

    def _dict(
        self,
        value,
    ) -> dict:

        if isinstance(
            value,
            dict,
        ):
            return value

        return {}

    # ---------------------------------------------------------

    def _emotion(
        self,
        value,
    ) -> EmotionLabel:

        try:

            return EmotionLabel[str(value).upper()]

        except Exception:

            return EmotionLabel.NEUTRAL

    # ---------------------------------------------------------

    def _fallback(
        self,
    ) -> Understanding:

        return Understanding(

            goal="conversation",

            intent="conversation",

            requires_tools=False,

            entities={},

            constraints={},

            confidence=0.2,

            emotional_tone=EmotionLabel.NEUTRAL,

        )