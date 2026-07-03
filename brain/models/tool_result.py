from dataclasses import dataclass, field


@dataclass(slots=True)
class ToolResult:

    success: bool

    output: str = ""

    data: dict = field(
        default_factory=dict
    )