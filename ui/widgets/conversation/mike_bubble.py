from __future__ import annotations

from ui.theme import colors

from ui.widgets.conversation.bubble_base import BubbleBase


class MikeBubble(BubbleBase):
    """
    Mike response bubble.
    """

    def __init__(
        self,
        text: str,
    ) -> None:

        super().__init__(
            title="Mike",
            text=text,
        )

        self.setStyleSheet(
            f"""
            QFrame#bubble {{

                background:{colors.SURFACE};

                border:none;

                border-radius:20px;

            }}

            QLabel#header {{

                background:transparent;

                color:{colors.TEXT_MUTED};

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