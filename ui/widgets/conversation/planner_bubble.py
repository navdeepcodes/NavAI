from __future__ import annotations

from ui.theme import colors

from ui.widgets.conversation.bubble_base import BubbleBase


class PlannerBubble(BubbleBase):
    """
    Planner reasoning bubble.
    """

    def __init__(
        self,
        text: str,
    ) -> None:

        super().__init__(
            title="Planner",
            text=text,
        )

        self.setStyleSheet(
            self.styleSheet()
            + f"""

QFrame#bubble {{

    background:#15130F;

}}

QLabel#header {{

    color:{colors.PLANNER};

}}
"""
        )