from __future__ import annotations

import re

from brain.session.conversation import Conversation
from brain.session.entity_tracker import EntityTracker
from brain.session.topic_tracker import TopicTracker


class Session:
    """
    Mike's short-term conversational state.

    Session is the single source of truth for everything
    remembered during the current conversation.

    Responsibilities
    ----------------
    • Store conversation
    • Store discovered entities
    • Store current topic
    • Store active task
    • Store recent tool results

    Session NEVER performs reasoning.
    """

    # =====================================================
    # Construction
    # =====================================================

    def __init__(self) -> None:

        self.conversation = Conversation()
        self.topic = TopicTracker()
        self.entities = EntityTracker()

        self.active_task: str | None = None

        self.tool_history: list[str] = []

        self.metadata: dict[str, object] = {}

    # =====================================================
    # Conversation
    # =====================================================

    def add_user(
        self,
        message: str,
    ) -> None:

        self.conversation.add_user(message)

        self._learn(message)

    # -----------------------------------------------------

    def add_assistant(
        self,
        message: str,
    ) -> None:

        self.conversation.add_assistant(message)

        self._learn(message)

    # -----------------------------------------------------

    def transcript(
        self,
        limit: int | None = None,
    ) -> str:

        return self.conversation.transcript(limit)

    # =====================================================
    # Topic
    # =====================================================

    @property
    def current_topic(self) -> str:

        return self.topic.current or ""

    # -----------------------------------------------------

    @current_topic.setter
    def current_topic(
        self,
        value: str,
    ) -> None:

        if value:

            self.topic.current = value

    # =====================================================
    # Tool History
    # =====================================================

    def add_tool_result(
        self,
        result: str,
    ) -> None:

        self.tool_history.append(result)

        self.tool_history = self.tool_history[-10:]

    # =====================================================
    # Learning
    # =====================================================

    def _learn(
        self,
        message: str,
    ) -> None:
        """
        Learn anything useful from the message.

        Today:
            • Person entities

        Future:
            • EntityExtractor
            • TopicExtractor
            • MemoryExtractor

        Session itself should never change.
        """

        self._learn_entities(message)

    # -----------------------------------------------------

    def _learn_entities(
        self,
        message: str,
    ) -> None:

        person = self._extract_person(message)

        if person:

            self.entities.set(
                "person",
                person,
            )

            self.current_topic = person

    # -----------------------------------------------------

    @staticmethod
    def _extract_person(
        message: str,
    ) -> str | None:
        """
        Temporary entity extraction.

        This method exists ONLY until the LLM-based
        EntityExtractor is implemented.
        """

        patterns = (

            r"(?:who\s+is|who's)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",

            r"about\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",

        )

        for pattern in patterns:

            match = re.search(
                pattern,
                message,
                flags=re.IGNORECASE,
            )

            if match:

                return match.group(1).strip()

        return None

    # =====================================================
    # Reset
    # =====================================================

    def reset(self) -> None:

        self.conversation.clear()

        self.topic.clear()

        self.entities.clear()

        self.active_task = None

        self.tool_history.clear()

        self.metadata.clear()