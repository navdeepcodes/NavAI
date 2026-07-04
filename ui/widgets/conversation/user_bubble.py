from __future__ import annotations

from ui.theme import colors

from ui.widgets.conversation.bubble_base import BubbleBase


class UserBubble(BubbleBase):
    """
    User message bubble.
    """

    def __init__(
        self,
        text: str,
    ) -> None:

        super().__init__(
            title="You",
            text=text,
        )

        self.setStyleSheet(
            f"""
            QFrame#bubble {{

                background:{colors.USER_BUBBLE};

                border:none;

                border-radius:20px;

            }}

            QLabel#header {{

                background:transparent;

                color:#B7C8FF;

                font-size:11px;

                font-weight:700;

            }}

            QLabel#content {{

                background:transparent;

                color:{colors.TEXT};

                font-size:15px;

                line-height:150%;

            }}
            """
        )