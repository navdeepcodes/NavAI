from __future__ import annotations

from ui.theme import colors
from ui.theme import typography

from ui.widgets.conversation.bubble_base import BubbleBase


class PlannerBubble(BubbleBase):

    def __init__(self, text: str) -> None:

        super().__init__(
            text=text,
            show_header=True,
            header_text="PLANNING",
        )

        self.setStyleSheet(
            f"""
            QFrame#bubble {{
                background: {colors.ACTION_SURFACE};
                border: 1px solid {colors.ACTION_BORDER};
                border-radius: 10px;
            }}

            QLabel#header {{
                color: {colors.WARNING};
                font-size: {typography.TINY}px;
                font-weight: 600;
                letter-spacing: 0.5px;
                background: transparent;
                border: none;
            }}

            QLabel#content {{
                color: {colors.TEXT_SECONDARY};
                font-size: {typography.SMALL}px;
                background: transparent;
                border: none;
            }}
            """
        )
