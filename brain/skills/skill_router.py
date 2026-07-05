from __future__ import annotations

from collections import defaultdict

from brain.cognition.models.cognition_state import CognitionState
from brain.skills.base_skill import BaseSkill
from brain.skills.skill_registry import SkillRegistry


class SkillRouter:
    """
    Selects a small set of candidate skills that are
    likely to handle the current cognition state.

    The router never executes skills.

    It only narrows the search space.
    """

    # -----------------------------------------------------

    def __init__(
        self,
        registry: SkillRegistry,
    ) -> None:

        self._registry = registry

        self._intent_index = self._build_index()

    # -----------------------------------------------------

    def _build_index(
        self,
    ) -> dict[str, list[BaseSkill]]:

        index: dict[str, list[BaseSkill]] = defaultdict(list)

        for skill in self._registry.skills.values():

            for example in skill.metadata.examples:

                index[
                    example.lower()
                ].append(skill)

        return index

    # -----------------------------------------------------

    def route(
        self,
        state: CognitionState,
    ) -> list[BaseSkill]:

        candidates: list[BaseSkill] = []

        intent = (
            state.intent or ""
        ).lower()

        if intent in self._intent_index:

            candidates.extend(
                self._intent_index[intent]
            )

        if not candidates:

            candidates.extend(
                self._registry.skills.values()
            )

        unique = []

        seen = set()

        for skill in candidates:

            name = skill.metadata.name

            if name in seen:

                continue

            seen.add(name)

            unique.append(skill)

        return unique