from __future__ import annotations

from brain.cognition.models.cognition_state import CognitionState

from brain.skills.skill_registry import SkillRegistry
from brain.skills.skill_result import SkillResult
from brain.skills.skill_router import SkillRouter


class SkillManager:
    """
    Executes the most appropriate skill for the current cognition state.

    Responsibilities
    ----------------
    • Ask the SkillRouter for candidate skills.
    • Select the highest-confidence skill.
    • Execute exactly one skill.
    • Never return None.
    """

    # -----------------------------------------------------

    def __init__(self) -> None:

        self.registry = SkillRegistry()

        self.router = SkillRouter(
            self.registry,
        )

    # -----------------------------------------------------

    def process(
        self,
        state: CognitionState,
    ) -> SkillResult:

        candidates = self.router.route(
            state,
        )

        best_skill = None

        best_score = 0.0

        # -------------------------------------------------
        # Evaluate only routed candidates
        # -------------------------------------------------

        for skill in candidates:

            try:

                confidence = float(
                    skill.can_handle(
                        state,
                    )
                )

            except Exception:

                continue

            if confidence > best_score:

                best_score = confidence

                best_skill = skill

        # -------------------------------------------------
        # No skill matched
        # -------------------------------------------------

        if best_skill is None:

            return SkillResult(

                handled=False,

                skill_name="",

                confidence=0.0,

                response="",

                metadata={
                    "reason": "no_matching_skill",
                },

            )

        # -------------------------------------------------
        # Execute selected skill
        # -------------------------------------------------

        try:

            result = best_skill.execute(
                state,
            )

        except Exception as exc:

            return SkillResult(

                handled=False,

                skill_name=best_skill.metadata.name,

                confidence=0.0,

                response="",

                metadata={
                    "error": "skill_execution_failed",
                    "exception": str(exc),
                },

            )

        # -------------------------------------------------
        # Defensive checks
        # -------------------------------------------------

        if result is None:

            return SkillResult(

                handled=False,

                skill_name=best_skill.metadata.name,

                confidence=0.0,

                response="",

                metadata={
                    "error": "skill_returned_none",
                },

            )

        if not result.skill_name:

            result.skill_name = best_skill.metadata.name

        if result.confidence <= 0:

            result.confidence = best_score

        if result.metadata is None:

            result.metadata = {}

        return result