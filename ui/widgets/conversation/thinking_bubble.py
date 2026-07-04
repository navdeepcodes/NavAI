from __future__ import annotations

from PySide6.QtCore import QTimer

from ui.widgets.conversation.bubble_base import BubbleBase


class ThinkingBubble(BubbleBase):
    """
    Animated thinking bubble.
    """

    STATES = (
        "Thinking",
        "Thinking.",
        "Thinking..",
        "Thinking...",
    )

    # =====================================================

    def __init__(self) -> None:

        super().__init__(
            title="Mike",
            text=self.STATES[0],
        )

        self._index = 0

        self._timer = QTimer(self)

        self._timer.timeout.connect(
            self._animate
        )

        self._timer.start(400)

    # =====================================================

    def _animate(self) -> None:

        self._index = (
            self._index + 1
        ) % len(self.STATES)

        self.set_text(
            self.STATES[self._index]
        )

    # =====================================================

    def stop(self) -> None:

        self._timer.stop()