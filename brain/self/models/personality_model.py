from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PersonalityModel:
    """
    Defines Mike's behaviour.
    """

    tone: str

    humor: bool

    proactive: bool

    concise: bool

    confidence: float

    formality: str