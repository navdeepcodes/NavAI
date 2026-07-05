from __future__ import annotations

from dataclasses import dataclass

from brain.cognition.models.cognition_state import CognitionState


@dataclass(slots=True)
class CapabilityDecision:

    capability: str

    confidence: float


class CapabilityReasoner:
    """
    Determines which capability Mike needs in order
    to satisfy the user's goal.

    This does NOT choose skills.

    It only answers:

        "What capability is required?"
    """

    def reason(
        self,
        state: CognitionState,
    ) -> CapabilityDecision:

        intent = (
            state.intent or ""
        ).lower()

        mapping = {

            "greeting": "conversation",

            "introduce": "identity",

            "search": "browser",

            "browse": "browser",

            "filesystem": "filesystem",

            "terminal": "terminal",

            "email": "email",

            "question": "conversation",

        }

        capability = mapping.get(
            intent,
            "conversation",
        )

        return CapabilityDecision(

            capability=capability,

            confidence=1.0,

        )