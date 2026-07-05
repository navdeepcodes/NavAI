from __future__ import annotations

from brain.session.session import Session


class ContextBuilder:
    """
    Builds conversational context for the LLM.

    Only relevant, recent context should be supplied.
    The current user message is NOT included here because
    it is passed separately to the LLM.
    """

    MAX_MESSAGES = 8
    MAX_TOOL_RESULTS = 3

    # =====================================================

    def build(
        self,
        *,
        session: Session,
        user_message: str,
    ) -> str:

        parts: list[str] = []

        # =================================================
        # Topic
        # =================================================

        if session.current_topic:

            parts.append(
                f"""Current Topic
-------------
{session.current_topic}"""
            )

        # =================================================
        # Entities
        # =================================================

        entities: dict = {}

        if hasattr(session.entities, "all"):

            entities = session.entities.all()

        elif hasattr(session.entities, "items"):

            entities = dict(session.entities.items())

        elif hasattr(session.entities, "_entities"):

            entities = dict(session.entities._entities)

        if entities:

            entity_text = "\n".join(
                f"{k}: {v}"
                for k, v in entities.items()
            )

            parts.append(
                f"""Known Entities
--------------
{entity_text}"""
            )

        # =================================================
        # Active Task
        # =================================================

        if session.active_task:

            parts.append(
                f"""Active Task
-----------
{session.active_task}"""
            )

        # =================================================
        # Recent Tool Results
        # =================================================

        if session.tool_history:

            history = session.tool_history[-self.MAX_TOOL_RESULTS :]

            parts.append(
                "Recent Tool Results\n"
                "-------------------\n"
                + "\n".join(history)
            )

        # =================================================
        # Recent Conversation
        # =================================================

        transcript = session.transcript()

        if transcript:

            lines = transcript.splitlines()

            if len(lines) > self.MAX_MESSAGES:

                lines = lines[-self.MAX_MESSAGES :]

            parts.append(
                "Recent Conversation\n"
                "-------------------\n"
                + "\n".join(lines)
            )

        return "\n\n".join(parts)