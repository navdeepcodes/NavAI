from __future__ import annotations

from brain.cognition.models.cognition_state import CognitionState
from brain.knowledge.identity import MIKE

from brain.skills.base_skill import BaseSkill
from brain.skills.skill_metadata import SkillMetadata
from brain.skills.skill_result import SkillResult


class IdentitySkill(BaseSkill):

    @property
    def metadata(self) -> SkillMetadata:

        return SkillMetadata(

            name="identity",

            description="Answers questions about Mike.",

            category="conversation",

            priority=95,

            examples=[

                "who are you",

                "what are you",

                "who built you",

                "who created you",

                "who made you",

                "tell me about yourself",

            ],

        )

    # ---------------------------------------------------------

    def can_handle(
        self,
        state: CognitionState,
    ) -> float:

        text = state.user_message.lower()

        identity_phrases = [

            "who are you",

            "what are you",

            "tell me about yourself",

            "introduce yourself",

        ]

        creator_phrases = [

            "who built you",

            "who made you",

            "who created you",

            "did navdeep build you",

            "your creator",

        ]

        if any(
            phrase in text
            for phrase in identity_phrases
        ):
            return 1.0

        if any(
            phrase in text
            for phrase in creator_phrases
        ):
            return 1.0

        if state.intent.lower() in {

            "introduce",

            "identity",

            "ask about creator",

        }:
            return 0.95

        return 0.0

    # ---------------------------------------------------------

    def execute(
        self,
        state: CognitionState,
    ) -> SkillResult:

        text = state.user_message.lower()

        if (
            "build" in text
            or "creator" in text
            or "made" in text
            or "created" in text
        ):

            reply = (
                f"I was created by {MIKE.creator}. "
                f"I'm the AI assistant for the {MIKE.project} project."
            )

        else:

            reply = (
                f"I'm {MIKE.name}, "
                f"codename {MIKE.codename}. "
                f"My purpose is {MIKE.purpose}"
            )

        return SkillResult(

            handled=True,

            skill_name=self.metadata.name,

            confidence=1.0,

            response=reply,

            metadata={},

        )