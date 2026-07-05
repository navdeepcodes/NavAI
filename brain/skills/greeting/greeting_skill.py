from __future__ import annotations

from brain.cognition.models.cognition_state import CognitionState

from brain.skills.base_skill import BaseSkill
from brain.skills.skill_metadata import SkillMetadata
from brain.skills.skill_result import SkillResult


class GreetingSkill(BaseSkill):
    """
    Greeting skill.

    This skill is intentionally lightweight.

    Responsibilities
    ----------------
    • Detect greeting conversations.
    • Tag the conversation for the ResponseEngine.

    It does NOT generate the greeting itself.
    """

    @property
    def metadata(self) -> SkillMetadata:

        return SkillMetadata(
            name="greeting",
            description="Handles greeting conversations.",
            category="conversation",
            priority=100,
            examples=[
                "hi",
                "hello",
                "hey",
                "hey mike",
                "yo",
                "sup",
                "what's up",
                "good morning",
                "good afternoon",
                "good evening",
            ],
        )

    # =====================================================

    def can_handle(
        self,
        state: CognitionState,
    ) -> float:

        intent = (state.intent or "").strip().upper()

        return 1.0 if intent == "GREETING" else 0.0

    # =====================================================

    def execute(
        self,
        state: CognitionState,
    ) -> SkillResult:

        return SkillResult(
            handled=True,
            skill_name=self.metadata.name,
            confidence=1.0,

            # ResponseEngine will generate the
            # actual greeting naturally.
            response="",

            metadata={
                "conversation_type": self.metadata.name,
            },
        )