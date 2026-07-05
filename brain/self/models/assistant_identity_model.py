from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AssistantIdentityModel:
    """
    Immutable identity of Mike.

    This represents who Mike is and never changes
    during runtime.
    """

    name: str

    project: str

    creator: str

    version: str

    purpose: str

    description: str

    motto: str