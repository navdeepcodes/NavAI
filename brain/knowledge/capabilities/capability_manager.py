from __future__ import annotations

from dataclasses import dataclass, field

from tools.tool_registry import ToolRegistry


# ==========================================================
# Capability
# ==========================================================


@dataclass(slots=True)
class Capability:

    tool: str

    description: str

    category: str

    permission: str

    actions: list[str] = field(
        default_factory=list,
    )


# ==========================================================
# Capability Manager
# ==========================================================


class CapabilityManager:
    """
    Single source of truth for Mike's capabilities.

    Capabilities are discovered dynamically from ToolRegistry.

    This class never hardcodes tools.
    """

    # ------------------------------------------------------

    def __init__(
        self,
        registry: ToolRegistry,
    ) -> None:

        self._registry = registry

        self._capabilities: list[Capability] = []

        self._prompt_cache = ""

        self.refresh()

    # ------------------------------------------------------

    def refresh(
        self,
    ) -> None:

        self._capabilities = self._discover()

        self._prompt_cache = self._build_prompt()

    # ------------------------------------------------------

    def _discover(
        self,
    ) -> list[Capability]:

        capabilities: list[Capability] = []

        for tool in self._registry.tools.values():

            metadata = tool.metadata

            permission = getattr(
                tool.permission,
                "name",
                str(tool.permission),
            )

            capabilities.append(

                Capability(

                    tool=metadata.name,

                    description=metadata.description,

                    category=metadata.category,

                    permission=permission,

                    actions=sorted(
                        tool.actions.keys()
                    ),

                )

            )

        capabilities.sort(
            key=lambda c: c.tool
        )

        return capabilities

    # ------------------------------------------------------

    @property
    def capabilities(
        self,
    ) -> list[Capability]:

        return self._capabilities

    # ------------------------------------------------------

    @property
    def count(
        self,
    ) -> int:

        return len(
            self._capabilities
        )

    # ------------------------------------------------------

    def get(
        self,
        tool: str,
    ) -> Capability | None:

        for capability in self._capabilities:

            if capability.tool == tool:

                return capability

        return None

    # ------------------------------------------------------

    def has_tool(
        self,
        tool: str,
    ) -> bool:

        return self.get(
            tool
        ) is not None

    # ------------------------------------------------------

    def has_action(
        self,
        tool: str,
        action: str,
    ) -> bool:

        capability = self.get(
            tool
        )

        if capability is None:

            return False

        return action in capability.actions

    # ------------------------------------------------------

    def get_actions(
        self,
        tool: str,
    ) -> list[str]:

        capability = self.get(
            tool
        )

        if capability is None:

            return []

        return capability.actions

    # ------------------------------------------------------

    def get_by_category(
        self,
        category: str,
    ) -> list[Capability]:

        return [

            capability

            for capability in self._capabilities

            if capability.category.lower()
            == category.lower()

        ]

    # ------------------------------------------------------

    def _build_prompt(
        self,
    ) -> str:

        if not self._capabilities:

            return "Mike currently has no installed capabilities."

        sections: list[str] = [

            "Available Capabilities"

        ]

        for capability in self._capabilities:

            sections.append(

                f"""
Tool: {capability.tool}

Description: {capability.description}

Category: {capability.category}

Permission: {capability.permission}

Actions:
- {"\n- ".join(capability.actions)}
""".strip()

            )

        return "\n\n".join(
            sections
        )

    # ------------------------------------------------------

    def to_prompt(
        self,
    ) -> str:

        return self._prompt_cache