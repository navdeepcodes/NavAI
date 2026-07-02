from dataclasses import dataclass, field

from typing import Dict, Any


@dataclass
class Action:

    type: str

    response: str

    tool: str | None = None

    action: str | None = None

    parameters: Dict[str, Any] = field(
        default_factory=dict
    )

    @classmethod
    def from_dict(cls, data):

        return cls(

            type=data.get("type", "chat"),

            response=data.get(
                "response",
                ""
            ),

            tool=data.get("tool"),

            action=data.get("action"),

            parameters=data.get(
                "parameters",
                {}
            )

        )

    @property
    def is_chat(self):

        return self.type == "chat"

    @property
    def is_tool(self):

        return self.type == "tool"