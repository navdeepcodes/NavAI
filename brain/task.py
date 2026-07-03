from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Task:

    id: int

    description: str

    tool: str | None = None

    arguments: Dict = field(default_factory=dict)

    completed: bool = False

    result: str = ""