from __future__ import annotations

from brain.self.capability import Capability


class CapabilityBuilder:
    """
    Converts ToolMetadata into Mike capabilities.
    """

    @staticmethod
    def build(metadata) -> Capability:

        return Capability(

            name=metadata.name,

            description=metadata.description,

            category=metadata.category,

            enabled=True,

            version="1.0",

            requires_permission=False,

        )