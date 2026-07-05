from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Capability:
    """
    Represents one capability Mike possesses.

    Capabilities describe WHAT Mike is capable of,
    not HOW the capability is implemented.
    """

    name: str

    description: str

    enabled: bool = True

    category: str = "general"

    version: str = "1.0"

    requires_permission: bool = False