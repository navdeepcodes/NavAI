from __future__ import annotations

from brain.knowledge.identity import MIKE
from brain.knowledge.environment import EnvironmentManager
from brain.knowledge.capabilities import CapabilityManager

from tools.tool_registry import ToolRegistry


class KnowledgeManager:
    """
    Central knowledge repository for Mike.

    Every subsystem (Understanding, Decision,
    Planning, Reasoning and Response) should obtain
    knowledge from here instead of constructing
    prompts independently.
    """

    # -----------------------------------------------------

    def __init__(self) -> None:

        self.tool_registry = ToolRegistry()

        self.identity = MIKE

        self.environment = EnvironmentManager()

        self.capabilities = CapabilityManager(
            self.tool_registry,
        )

    # -----------------------------------------------------

    def refresh(self) -> None:

        self.environment.refresh()

        self.capabilities.refresh()

    # -----------------------------------------------------

    @property
    def system_context(self) -> str:

        sections = [

            self.identity.to_prompt(),

            self.environment.to_prompt(),

            self.capabilities.to_prompt(),

        ]

        return "\n\n".join(sections)