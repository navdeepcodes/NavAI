from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Task:

    # ---------------------------------------------------------

    id: int

    description: str

    tool: str | None = None

    action: str | None = None

    arguments: dict[str, Any] = field(

        default_factory=dict

    )

    completed: bool = False

    result: str | None = None

    # ---------------------------------------------------------

    @property
    def executable(self) -> bool:

        return self.tool is not None

    # ---------------------------------------------------------

    def mark_complete(

        self,

        result: Any = None

    ):

        self.completed = True

        if result is not None:

            self.result = str(result)

    # ---------------------------------------------------------

    def mark_failed(

        self,

        error: Exception | str

    ):

        self.completed = False

        self.result = str(error)