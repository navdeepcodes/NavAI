from __future__ import annotations

import json

from logs.logger import logger

from brain.intelligence.analysis import CognitiveAnalysis
from brain.intelligence.models import Emotion
from brain.intelligence.enums import (
    EmotionLabel,
    ConversationStyle,
)


class CognitiveParser:
    """
    Converts the LLM's JSON response into a CognitiveAnalysis object.
    """

    # ---------------------------------------------------------

    def parse(
        self,
        text: str,
    ) -> CognitiveAnalysis | None:

        try:

            text = self._clean(text)

            data = json.loads(text)

            emotion = data.get("emotion", {})

            return CognitiveAnalysis(

                goal=data.get("goal", ""),

                intent=data.get("intent", ""),

                requires_tools=data.get(

                    "requires_tools",

                    False,

                ),

                emotion=Emotion(

                    label=EmotionLabel(

                        emotion.get(

                            "label",

                            "neutral",

                        )

                    ),

                    confidence=emotion.get(

                        "confidence",

                        1.0,

                    ),

                    intensity=emotion.get(

                        "intensity",

                        0.5,

                    ),

                    explanation=emotion.get(

                        "explanation",

                        "",

                    ),

                    response_hint=emotion.get(

                        "response_hint",

                        "",

                    ),

                ),

                urgency=data.get(

                    "urgency",

                    "normal",

                ),

                conversation_style=ConversationStyle(

                    data.get(

                        "conversation_style",

                        "friendly",

                    )

                ),

                confidence=data.get(

                    "confidence",

                    1.0,

                ),

            )

        except Exception as e:

            logger.exception(e)

            return None

    # ---------------------------------------------------------

    def _clean(
        self,
        text: str,
    ) -> str:

        text = text.strip()

        if text.startswith("```"):

            lines = text.splitlines()

            if lines:

                lines = lines[1:]

            if lines and lines[-1].startswith("```"):

                lines = lines[:-1]

            text = "\n".join(lines)

        return text.strip()