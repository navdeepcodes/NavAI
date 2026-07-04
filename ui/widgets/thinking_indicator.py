from __future__ import annotations

from enum import Enum

from PySide6.QtCore import (
    Property,
    QPropertyAnimation,
    QEasingCurve,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.theme import colors


class ThinkingState(Enum):

    IDLE = "idle"

    THINKING = "thinking"

    EXECUTING = "executing"

    LOCAL = "local"

    LISTENING = "listening"


class ThinkingIndicator(QWidget):
    """
    Mike's signature animation.

    A subtle pulsing ring that changes color
    depending on Mike's cognitive state.

    This is the ONLY animation in the UI.
    """

    # ---------------------------------------------------------

    def __init__(self):

        super().__init__()

        self.setFixedSize(18, 18)

        self._radius = 6.0

        self._state = ThinkingState.IDLE

        self._color = QColor(colors.TEXT_SECONDARY)

        self.animation = QPropertyAnimation(

            self,

            b"radius"

        )

        self.animation.setDuration(1200)

        self.animation.setStartValue(5.5)

        self.animation.setEndValue(8.0)

        self.animation.setLoopCount(-1)

        self.animation.setEasingCurve(

            QEasingCurve.InOutSine

        )

    # ---------------------------------------------------------
    # Radius Property
    # ---------------------------------------------------------

    def get_radius(self):

        return self._radius

    def set_radius(

        self,

        value,

    ):

        self._radius = value

        self.update()

    radius = Property(

        float,

        get_radius,

        set_radius

    )

    # ---------------------------------------------------------
    # State
    # ---------------------------------------------------------

    def set_state(

        self,

        state: ThinkingState,

    ):

        self._state = state

        palette = {

            ThinkingState.IDLE:

                colors.TEXT_SECONDARY,

            ThinkingState.THINKING:

                colors.ACCENT,

            ThinkingState.EXECUTING:

                colors.SUCCESS,

            ThinkingState.LOCAL:

                colors.WARNING,

            ThinkingState.LISTENING:

                colors.ONLINE,

        }

        self._color = QColor(

            palette[state]

        )

        if state == ThinkingState.IDLE:

            self.animation.stop()

            self._radius = 6

            self.update()

        else:

            self.animation.start()

    # ---------------------------------------------------------

    def paintEvent(

        self,

        event,

    ):

        painter = QPainter(self)

        painter.setRenderHint(

            QPainter.Antialiasing

        )

        pen = QPen(

            self._color,

            2,

        )

        painter.setPen(pen)

        center = self.rect().center()

        painter.drawEllipse(

            center,

            self._radius,

            self._radius,

        )