from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ToolContext:
    """
    Shared runtime context passed to every tool execution.

    This object contains information about the current user,
    session, runtime, and execution environment.
    """

    # ---------------------------------------------------------
    # Identity
    # ---------------------------------------------------------

    user: str = "default"

    session_id: str = ""

    # ---------------------------------------------------------
    # Runtime
    # ---------------------------------------------------------

    working_directory: Path = field(
        default_factory=Path.cwd
    )

    current_provider: str = ""

    # ---------------------------------------------------------
    # Conversation
    # ---------------------------------------------------------

    conversation_id: str = ""

    # ---------------------------------------------------------
    # Shared Objects
    # ---------------------------------------------------------

    runtime: Any = None

    memory: Any = None

    permission_manager: Any = None

    # ---------------------------------------------------------
    # Scratch Storage
    # ---------------------------------------------------------

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # ---------------------------------------------------------

    def get(
        self,
        key: str,
        default=None
    ):
        return self.metadata.get(
            key,
            default
        )

    # ---------------------------------------------------------

    def set(
        self,
        key: str,
        value: Any
    ):

        self.metadata[key] = value

    # ---------------------------------------------------------

    def update(
        self,
        **kwargs
    ):

        self.metadata.update(kwargs)

    # ---------------------------------------------------------

    def clear(self):

        self.metadata.clear()