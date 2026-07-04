from __future__ import annotations

from ui.theme import colors

from ui.widgets.conversation.bubble_base import BubbleBase


class ToolBubble(BubbleBase):
    """
    Tool execution bubble.
    """

    def __init__(
        self,
        text: str,
    ) -> None:

        super().__init__(
            title="Tool",
            text=text,
        )

        self.setStyleSheet(
            self.styleSheet()
            + f"""

QFrame#bubble {{

    background:#121417;

}}

QLabel#header {{

    color:{colors.GROQ};

}}
"""
        )