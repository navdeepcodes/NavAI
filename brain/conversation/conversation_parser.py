from __future__ import annotations

import json
import logging

from brain.conversation.conversation_models import ConversationState

logger = logging.getLogger(__name__)


class ConversationParser:

    def parse(
        self,
        raw: str,
    ) -> ConversationState:

        try:

            raw = raw.strip()

            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                raw = raw.rsplit("```", 1)[0]

            data = json.loads(raw)

            return ConversationState(

                tone=data.get("tone", "natural"),

                empathy=float(data.get("empathy", 0.5)),

                enthusiasm=float(data.get("enthusiasm", 0.5)),

                confidence=float(data.get("confidence", 0.8)),

                curiosity=float(data.get("curiosity", 0.5)),

                humor=float(data.get("humor", 0.2)),

                patience=float(data.get("patience", 1.0)),

                formality=float(data.get("formality", 0.4)),

                warmth=float(data.get("warmth", 0.7)),

                ask_follow_up=bool(data.get("ask_follow_up", False)),

                acknowledge_user=bool(data.get("acknowledge_user", False)),

                celebrate=bool(data.get("celebrate", False)),

                apologize=bool(data.get("apologize", False)),

                reassure=bool(data.get("reassure", False)),

                challenge_user=bool(data.get("challenge_user", False)),

                response_length=data.get("response_length", "medium"),

                communication_style=data.get(
                    "communication_style",
                    "human",
                ),

                relationship_state=data.get(
                    "relationship_state",
                    "neutral",
                ),

                reasoning=data.get("reasoning", ""),

            )

        except Exception:

            logger.exception(
                "Conversation parsing failed."
            )

            return ConversationState()