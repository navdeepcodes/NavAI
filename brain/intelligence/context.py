from __future__ import annotations

from brain.intelligence.models import Context


class ContextManager:
    """
    Maintains Mike's working context during a conversation.

    This is NOT long-term memory.
    It only stores information relevant to the
    current interaction/session.
    """

    # ---------------------------------------------------------

    def __init__(self):

        self._context = Context()

    # ---------------------------------------------------------
    # Context Access
    # ---------------------------------------------------------

    @property
    def current(self) -> Context:

        return self._context

    # ---------------------------------------------------------
    # Current Task
    # ---------------------------------------------------------

    def set_task(
        self,
        task: str,
    ) -> None:

        self._context.current_task = task

    # ---------------------------------------------------------

    def clear_task(self) -> None:

        self._context.current_task = ""

    # ---------------------------------------------------------
    # Conversation History
    # ---------------------------------------------------------

    def add_message(
        self,
        message: str,
    ) -> None:

        self._context.previous_messages.append(message)

        # Keep only the latest 20 messages.
        self._context.previous_messages = (
            self._context.previous_messages[-20:]
        )

    # ---------------------------------------------------------
    # Tool Results
    # ---------------------------------------------------------

    def add_tool_result(
        self,
        result,
    ) -> None:

        self._context.recent_tool_results.append(result)

        # Keep only recent results.
        self._context.recent_tool_results = (
            self._context.recent_tool_results[-10:]
        )

    # ---------------------------------------------------------
    # Active Project
    # ---------------------------------------------------------

    def set_active_project(
        self,
        project: str,
    ) -> None:

        self._context.active_project = project

    # ---------------------------------------------------------

    def clear_active_project(self) -> None:

        self._context.active_project = None

    # ---------------------------------------------------------
    # Working Directory
    # ---------------------------------------------------------

    def set_working_directory(
        self,
        directory: str,
    ) -> None:

        self._context.working_directory = directory

    # ---------------------------------------------------------
    # Reset
    # ---------------------------------------------------------

    def reset(self) -> None:

        self._context = Context()