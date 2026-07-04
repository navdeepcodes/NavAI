from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
)

from ui.theme import colors, fonts


class StatusBar(QFrame):
    """
    Bottom status bar.

    Displays runtime information.
    """

    # ---------------------------------------------------------

    def __init__(self):

        super().__init__()

        self._build()

    # ---------------------------------------------------------

    def _build(self):

        self.setFixedHeight(32)

        self.setStyleSheet(
            f"""
            QFrame {{
                background:{colors.BACKGROUND};
                border:none;
                border-top:1px solid {colors.BORDER};
            }}
            """
        )

        layout = QHBoxLayout(self)

        layout.setContentsMargins(

            24,

            0,

            24,

            0,

        )

        self.label = QLabel(

            "Groq • Online • Fast • Memory Ready"

        )

        self.label.setFont(

            fonts.SMALL

        )

        self.label.setAlignment(

            Qt.AlignLeft | Qt.AlignVCenter

        )

        self.label.setStyleSheet(

            f"""

            color:{colors.TEXT_MUTED};

            """

        )

        layout.addWidget(

            self.label

        )

    # ---------------------------------------------------------

    def set_text(

        self,

        text: str,

    ):

        self.label.setText(

            text

        )