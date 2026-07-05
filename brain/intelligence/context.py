from __future__ import annotations

from brain.conversation.conversation_memory import ConversationMemory
from brain.intelligence.models import Context


class ContextManager:
    """
    Maintains Mike's short-term working context.

    Responsibilities
    ----------------
    • Session conversation memory
    • Current task
    • Tool results
    • Active project
    • Working directory

    This is NOT long-term memory.
    """

    # =====================================================

    def __init__(self) -> None:

        self._context = Context()

        self.conversation = ConversationMemory()

    # =====================================================
    # Context
    # =====================================================

    @property
    def current(self) -> Context:

        return self._context

    # =====================================================
    # Current Task
    # =====================================================

    def set_task(
        self,
        task: str,
    ) -> None:

        self._context.current_task = task

    # -----------------------------------------------------

    def clear_task(
        self,
    ) -> None:

        self._context.current_task = ""

    # =====================================================
    # Conversation
    # =====================================================

    def add_user_message(
        self,
        message: str,
    ) -> None:

        self.conversation.add_user(message)

    # -----------------------------------------------------

    def add_assistant_message(
        self,
        message: str,
    ) -> None:

        self.conversation.add_assistant(message)

    # -----------------------------------------------------

    def conversation_context(
        self,
        limit: int = 10,
    ) -> str:

        return self.conversation.build_context(limit)

    # -----------------------------------------------------

    def transcript(
        self,
        limit: int = 10,
    ) -> str:

        return self.conversation.transcript(limit)

    # -----------------------------------------------------

    def set_topic(
        self,
        topic: str,
    ) -> None:

        self.conversation.set_topic(topic)

    # =====================================================
    # Tool Results
    # =====================================================

    def add_tool_result(
        self,
        result,
    ) -> None:

        self._context.recent_tool_results.append(result)

        self._context.recent_tool_results = (
            self._context.recent_tool_results[-10:]
        )

    # =====================================================
    # Active Project
    # =====================================================

    def set_active_project(
        self,
        project: str,
    ) -> None:

        self._context.active_project = project

    # -----------------------------------------------------

    def clear_active_project(
        self,
    ) -> None:

        self._context.active_project = None

    # =====================================================
    # Working Directory
    # =====================================================

    def set_working_directory(
        self,
        directory: str,
    ) -> None:

        self._context.working_directory = directory

    # =====================================================
    # Reset
    # =====================================================

    def reset(
        self,
    ) -> None:

        self._context = Context()

        self.conversation.clear()