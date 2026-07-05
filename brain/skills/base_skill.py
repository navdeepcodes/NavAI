from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from brain.skills.skill_metadata import SkillMetadata
from brain.skills.skill_result import SkillResult

from brain.cognition.models.cognition_state import CognitionState


class BaseSkill(ABC):

    @property
    @abstractmethod
    def metadata(
        self,
    ) -> SkillMetadata:
        ...

    @abstractmethod
    def can_handle(
        self,
        state: CognitionState,
    ) -> float:
        """
        Return confidence between

        0.0 and 1.0
        """
        ...

    @abstractmethod
    def execute(
        self,
        state: CognitionState,
    ) -> SkillResult:
        ...