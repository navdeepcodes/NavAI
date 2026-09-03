from __future__ import annotations

from ui.theme import colors
from ui.theme import typography

from ui.widgets.conversation.bubble_base import BubbleBase


class SystemBubble(BubbleBase):

    def __init__(self, text: str) -> None:

        super().__init__(text=text)

        self.setStyleSheet(
            f"""
            QFrame#bubble {{
                background: transparent;
                border: none;
                border-radius: 0;
            }}

            QLabel#content {{
                color: {colors.TEXT_MUTED};
                font-size: {typography.SMALL}px;
                background: transparent;
                border: none;
            }}
            """
        )
