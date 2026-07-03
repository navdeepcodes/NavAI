from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class ToolMetadata:
    """
    Immutable metadata describing a tool.

    Metadata is loaded during tool discovery and remains
    constant for the lifetime of the application.
    """

    # ---------------------------------------------------------
    # Identity
    # ---------------------------------------------------------

    name: str

    description: str

    category: str = "general"

    # ---------------------------------------------------------
    # Versioning
    # ---------------------------------------------------------

    version: str = "1.0.0"

    author: str = "NavAI"

    # ---------------------------------------------------------
    # Configuration
    # ---------------------------------------------------------

    enabled: bool = True

    requires_permission: bool = True

    dangerous: bool = False

    # ---------------------------------------------------------
    # Search / Discovery
    # ---------------------------------------------------------

    tags: list[str] = field(
        default_factory=list
    )

    # ---------------------------------------------------------

    def has_tag(
        self,
        tag: str
    ) -> bool:

        return tag.lower() in {

            t.lower()

            for t in self.tags

        }