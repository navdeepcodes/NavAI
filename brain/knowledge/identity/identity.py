from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field


@dataclass(slots=True)
class Identity:
    """
    Canonical identity of Mike.

    This is the single source of truth for who Mike is.
    Every component (skills, prompts, responses, memory)
    should reference this object instead of hardcoding values.
    """

    # =====================================================
    # Basic Information
    # =====================================================

    name: str

    codename: str

    version: str

    creator: str

    project: str

    # =====================================================
    # Purpose
    # =====================================================

    mission: str

    purpose: str

    # =====================================================
    # Behaviour
    # =====================================================

    personality: list[str] = field(default_factory=list)

    principles: list[str] = field(default_factory=list)

    capabilities: list[str] = field(default_factory=list)

    limitations: list[str] = field(default_factory=list)

    goals: list[str] = field(default_factory=list)

    # =====================================================

    @staticmethod
    def _section(
        title: str,
        values: list[str],
    ) -> str:

        if not values:
            return f"{title}\nNone"

        return (
            f"{title}\n"
            + "\n".join(f"- {x}" for x in values)
        )

    # =====================================================

    def to_prompt(self) -> str:

        return f"""
Identity

Name: {self.name}
Codename: {self.codename}
Project: {self.project}
Version: {self.version}
Creator: {self.creator}

Mission

{self.mission}

Purpose

{self.purpose}

{self._section("Personality", self.personality)}

{self._section("Principles", self.principles)}

{self._section("Capabilities", self.capabilities)}

{self._section("Limitations", self.limitations)}

{self._section("Goals", self.goals)}
""".strip()

    # =====================================================

    def to_dict(self) -> dict:

        return asdict(self)

    # =====================================================

    def __str__(self) -> str:

        return self.name