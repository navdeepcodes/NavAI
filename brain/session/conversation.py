from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Turn:
    """
    Represents one conversational exchange.
    """

    user: str

    assistant: str = ""

    created_at: datetime = field(
        default_factory=datetime.utcnow,
    )


class Conversation:
    """
    Stores the complete conversation.

    Responsibilities
    ----------------
    • Store conversation turns
    • Return recent transcript
    • Maintain history size

    Never
    -----
    • Resolve references
    • Detect topics
    • Perform reasoning
    """

    # =====================================================

    def __init__(
        self,
        max_turns: int = 30,
    ) -> None:

        self.max_turns = max_turns
        self.turns: list[Turn] = []

    # =====================================================
    # Conversation
    # =====================================================

    def add_user(
        self,
        message: str,
    ) -> None:

        self.turns.append(
            Turn(user=message),
        )

        self._trim()

    # -----------------------------------------------------

    def add_assistant(
        self,
        message: str,
    ) -> None:

        if not self.turns:
            return

        self.turns[-1].assistant = message

    # =====================================================
    # Transcript
    # =====================================================

    def transcript(
        self,
        limit: int | None = 12,
    ) -> str:

        if limit is None:
            turns = self.turns
        else:
            turns = self.turns[-limit:]

        lines: list[str] = []

        for turn in turns:

            lines.append(
                f"User: {turn.user}"
            )

            if turn.assistant:

                lines.append(
                    f"Mike: {turn.assistant}"
                )

        return "\n".join(lines)

    # =====================================================
    # Convenience
    # =====================================================

    @property
    def last_user_message(
        self,
    ) -> str | None:

        if not self.turns:
            return None

        return self.turns[-1].user

    # -----------------------------------------------------

    @property
    def last_assistant_message(
        self,
    ) -> str | None:

        if not self.turns:
            return None

        return self.turns[-1].assistant

    # =====================================================
    # Maintenance
    # =====================================================

    def clear(
        self,
    ) -> None:

        self.turns.clear()

    # -----------------------------------------------------

    def _trim(
        self,
    ) -> None:

        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]