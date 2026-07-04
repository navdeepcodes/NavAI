from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.theme import colors, fonts


class Message(QWidget):
    """
    Conversation message.

    Minimal.
    No cards.
    No borders.
    No bubbles.

    Typography and whitespace create the hierarchy.
    """

    # ---------------------------------------------------------

    def __init__(
        self,
        author: str,
        content: str,
    ):

        super().__init__()

        self.author = author.upper()

        self.content = content

        self._build()

    # ---------------------------------------------------------

    def _build(self):

        layout = QVBoxLayout(self)

        layout.setContentsMargins(

            0,

            24,

            0,

            12,

        )

        layout.setSpacing(10)

        # -------------------------------------------------
        # Author
        # -------------------------------------------------

        author = QLabel(

            self.author

        )

        author.setFont(

            fonts.STATUS

        )

        author.setStyleSheet(

            f"""

            color:{colors.TEXT_SECONDARY};

            letter-spacing:2px;

            font-weight:600;

            """

        )

        layout.addWidget(author)

        # -------------------------------------------------
        # Content
        # -------------------------------------------------

        body = QLabel(

            self.content

        )

        body.setWordWrap(True)

        body.setTextInteractionFlags(

            Qt.TextSelectableByMouse

        )

        body.setFont(

            fonts.MESSAGE

        )

        body.setStyleSheet(

            f"""

            color:{colors.TEXT};

            background:transparent;

            border:none;

            padding:0px;

            """

        )

        layout.addWidget(body)