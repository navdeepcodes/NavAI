from __future__ import annotations

from ui.theme import colors

from ui.widgets.conversation.bubble_base import BubbleBase


class SystemBubble(BubbleBase):
    """
    Runtime / system information.
    """

    def __init__(
        self,
        text: str,
    ) -> None:

        super().__init__(
            title="System",
            text=text,
        )

        self.setStyleSheet(
            self.styleSheet()
            + f"""

QFrame#bubble {{

    background:#141414;

}}

QLabel#header {{

    color:{colors.TEXT_MUTED};

}}
"""
        )