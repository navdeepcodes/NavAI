from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QHBoxLayout,
)

from ui.theme import colors
from ui.theme import typography


class ThinkingBubble(QFrame):

    STATES = (
        "Mike is working",
        "Mike is working .",
        "Mike is working . .",
        "Mike is working . . .",
    )

    def __init__(self) -> None:

        super().__init__()

        self.setObjectName("thinking")

        self.setSizePolicy(
            QSizePolicy.Maximum,
            QSizePolicy.Fixed,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(0)

        self._label = QLabel(self.STATES[0])
        self._label.setObjectName("thinking_text")

        layout.addWidget(self._label)

        self.setStyleSheet(
            f"""
            QFrame#thinking {{
                background: transparent;
                border: none;
            }}

            QLabel#thinking_text {{
                color: {colors.TEXT_MUTED};
                font-size: {typography.SMALL}px;
                background: transparent;
                border: none;
            }}
            """
        )

        self._index = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(500)

    def _animate(self) -> None:

        self._index = (self._index + 1) % len(self.STATES)
        self._label.setText(self.STATES[self._index])

    def stop(self) -> None:

        self._timer.stop()

    # BubbleBase compatibility

    def set_text(self, text: str) -> None:
        self._label.setText(text)

    def append_text(self, text: str) -> None:
        self._label.setText(self._label.text() + text)

    def text(self) -> str:
        return self._label.text()
