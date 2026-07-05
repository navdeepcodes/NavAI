from __future__ import annotations


class TopicTracker:
    """
    Tracks the current conversation topic.

    Only stores the active topic.
    """

    def __init__(self) -> None:

        self.current: str = ""

    # -----------------------------------------------------

    def update(
        self,
        topic: str | None,
    ) -> None:

        if topic:

            self.current = topic.strip()

    # -----------------------------------------------------

    def clear(
        self,
    ) -> None:

        self.current = ""