from __future__ import annotations

from brain.session.reference_resolver import ReferenceResolver
from brain.session.session import Session


class ConversationResolver:
    """
    Resolves conversational references before the LLM sees the message.

    Responsibilities
    ----------------
    • Resolve pronouns ("he", "it", "they")
    • Resolve conversational follow-ups
    • Return a self-contained user message

    This class NEVER performs reasoning.
    """

    # =====================================================

    def __init__(self) -> None:

        self.reference = ReferenceResolver()

    # =====================================================

    def resolve(
        self,
        *,
        session: Session,
        message: str,
    ) -> str:

        resolved = message.strip()

        # ---------------------------------------------
        # Resolve pronouns / entities
        # ---------------------------------------------

        resolved = self.reference.resolve(
            resolved,
            session,
        )

        # ---------------------------------------------
        # Resolve follow-up messages
        # ---------------------------------------------

        resolved = self._resolve_followups(
            message=resolved,
            session=session,
        )

        return resolved

    # =====================================================

    def _resolve_followups(
        self,
        *,
        message: str,
        session: Session,
    ) -> str:

        lower = message.lower().strip()

        previous_user = (
            session.conversation.last_user_message or ""
        )

        previous_assistant = (
            session.conversation.last_assistant_message or ""
        )

        topic = session.current_topic

        # -------------------------------------------------
        # harder
        # -------------------------------------------------

        if lower == "harder":

            if topic:
                return f"Give me a harder example of {topic}."

            return "Give me a harder example."

        # -------------------------------------------------
        # easier
        # -------------------------------------------------

        if lower == "easier":

            if topic:
                return f"Give me an easier example of {topic}."

            return "Give me an easier example."

        # -------------------------------------------------
        # one more / again / another
        # -------------------------------------------------

        if lower in {
            "again",
            "another",
            "one more",
            "more",
        }:

            if topic:
                return f"Give me another example of {topic}."

            if previous_user:
                return f"Continue: {previous_user}"

            return message

        # -------------------------------------------------
        # continue
        # -------------------------------------------------

        if lower == "continue":

            if previous_assistant:
                return f"Continue from: {previous_assistant}"

            return message

        # -------------------------------------------------
        # why
        # -------------------------------------------------

        if lower in {
            "why",
            "why?",
        }:

            if previous_assistant:
                return f"Explain why: {previous_assistant}"

            return message

        # -------------------------------------------------
        # instead
        # -------------------------------------------------

        if lower.startswith("instead"):

            if previous_user:
                return f"{previous_user} {message}"

            return message

        # -------------------------------------------------
        # same
        # -------------------------------------------------

        if lower == "same":

            if previous_user:
                return previous_user

            return message

        # -------------------------------------------------
        # default
        # -------------------------------------------------

        return message