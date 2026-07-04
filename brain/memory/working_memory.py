from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class WorkingMemory:
    """
    Mike's short-term memory.

    Stores the current conversational and task state.

    This memory is temporary and is never persisted.
    """

    # ---------------------------------------------------------
    # Conversation
    # ---------------------------------------------------------

    current_user_message: str = ""

    last_response: str = ""

    conversation_history: list[str] = field(

        default_factory=list

    )

    # ---------------------------------------------------------
    # Task
    # ---------------------------------------------------------

    current_goal: str = ""

    current_task: str = ""

    current_project: str = ""

    # ---------------------------------------------------------
    # Context
    # ---------------------------------------------------------

    active_tools: list[str] = field(

        default_factory=list

    )

    recent_results: list[Any] = field(

        default_factory=list

    )

    temporary_notes: list[str] = field(

        default_factory=list

    )

    entities: dict[str, Any] = field(

        default_factory=dict

    )

    # ---------------------------------------------------------
    # Session
    # ---------------------------------------------------------

    session_started: datetime = field(

        default_factory=datetime.utcnow

    )

    last_updated: datetime = field(

        default_factory=datetime.utcnow

    )

    # ---------------------------------------------------------

    def update(self):

        self.last_updated = datetime.utcnow()

    # ---------------------------------------------------------

    def add_message(

        self,

        message: str,

    ):

        self.current_user_message = message

        self.conversation_history.append(

            message

        )

        self.update()

    # ---------------------------------------------------------

    def add_response(

        self,

        response: str,

    ):

        self.last_response = response

        self.update()

    # ---------------------------------------------------------

    def add_result(

        self,

        result: Any,

    ):

        self.recent_results.append(

            result

        )

        self.update()

    # ---------------------------------------------------------

    def clear(self):

        self.current_user_message = ""

        self.last_response = ""

        self.current_goal = ""

        self.current_task = ""

        self.active_tools.clear()

        self.recent_results.clear()

        self.temporary_notes.clear()

        self.entities.clear()

        self.update()