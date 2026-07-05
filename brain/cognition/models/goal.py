from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Goal:
    """
    A structured representation of what the user wants.

    Unlike an intent, a goal captures the semantic objective
    independent of how the user phrased it.

    Examples
    --------
    User:
        "Open Chrome"

    Goal(
        action="open",
        target="Google Chrome"
    )

    ----------------------------

    User:
        "Tell me more about him"

    Goal(
        action="learn",
        target="Elon Musk"
    )

    ----------------------------

    User:
        "Create a folder called AI"

    Goal(
        action="create",
        target="folder",
        name="AI"
    )
    """

    # =====================================================
    # Core
    # =====================================================

    action: str

    target: str | None = None

    # =====================================================
    # Optional semantic fields
    # =====================================================

    subject: str | None = None

    object: str | None = None

    name: str | None = None

    destination: str | None = None

    query: str | None = None

    value: Any | None = None

    # =====================================================
    # Extra data
    # =====================================================

    parameters: dict[str, Any] = field(
        default_factory=dict
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # =====================================================

    @property
    def is_empty(
        self,
    ) -> bool:

        return (
            self.action == ""
            and self.target is None
        )

    # =====================================================

    def to_dict(
        self,
    ) -> dict[str, Any]:

        return {
            "action": self.action,
            "target": self.target,
            "subject": self.subject,
            "object": self.object,
            "name": self.name,
            "destination": self.destination,
            "query": self.query,
            "value": self.value,
            "parameters": self.parameters,
            "metadata": self.metadata,
        }

    # =====================================================

    @classmethod
    def empty(
        cls,
    ) -> "Goal":

        return cls(
            action="",
        )