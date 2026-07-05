from __future__ import annotations

from brain.self.capability import Capability
from brain.self.capability_builder import CapabilityBuilder


class CapabilityRegistry:

    def __init__(self):

        self._capabilities: dict[str, Capability] = {}

    # --------------------------------------------

    def register(self, capability: Capability):

        self._capabilities[
            capability.name.lower()
        ] = capability

    # --------------------------------------------

    def register_tool(self, tool):

        capability = CapabilityBuilder.build(
            tool.metadata
        )

        self.register(capability)

    # --------------------------------------------

    def unregister(self, name: str):

        self._capabilities.pop(
            name.lower(),
            None,
        )

    # --------------------------------------------

    def has(self, name: str):

        return (
            name.lower()
            in self._capabilities
        )

    # --------------------------------------------

    def get(self, name: str):

        return self._capabilities.get(
            name.lower()
        )

    # --------------------------------------------

    def all(self):

        return list(
            self._capabilities.values()
        )

    # --------------------------------------------

    def enabled(self):

        return [

            c

            for c

            in self._capabilities.values()

            if c.enabled

        ]