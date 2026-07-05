from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityModel:
    """
    Represents a single capability Mike possesses.
    """

    name: str

    description: str

    enabled: bool = True