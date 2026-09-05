from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
)

from ui.theme import colors, spacing


# ==========================================================
# Task State
# ==========================================================

class TaskState(Enum):

    IDLE = "Idle"

    RUNNING = "Running"

    COMPLETED = "Completed"

    FAILED = "Failed"


# ==========================================================
# Task Card
# ==========================================================

class TaskCard(QFrame):
    """
    Represents one execution performed by Mike.

    One user request = One TaskCard.

    Future:
    --------
    • Streaming
    • Planner timeline
    • Tool execution
    • Vision
    • Browser actions
    • File operations
    """

    # -----------------------------------------------------

    def __init__(
        self,
        instruction: str,
    ) -> None:

        super().__init__()

        self._provider = "—"

        self._model = "—"

        self._latency = "—"

        self._state = TaskState.RUNNING

        self._instruction = instruction

        self._response = ""

        self._build_ui()

        self._apply_theme()

    # =====================================================
    # UI
    # =====================================================

    def _build_ui(self) -> None:

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            20,
            18,
            20,
            18,
        )

        layout.setSpacing(12)

        # -------------------------------------------------
        # Instruction
        # -------------------------------------------------

        self.instruction = QLabel(
            self._instruction.upper()
        )

        font = QFont()

        font.setPointSize(12)

        font.setBold(True)

        self.instruction.setFont(font)

        layout.addWidget(
            self.instruction
        )

        # -------------------------------------------------
        # Provider
        # -------------------------------------------------

        self.provider = QLabel(
            "Provider      —"
        )

        layout.addWidget(
            self.provider
        )

        # -------------------------------------------------

        self.model = QLabel(
            "Model         —"
        )

        layout.addWidget(
            self.model
        )

        # -------------------------------------------------

        self.state = QLabel(
            "Status        Running"
        )

        layout.addWidget(
            self.state
        )

        # -------------------------------------------------

        self.latency = QLabel(
            "Latency       —"
        )

        layout.addWidget(
            self.latency
        )

        # -------------------------------------------------

        self.separator = QFrame()

        self.separator.setFrameShape(
            QFrame.HLine
        )

        layout.addWidget(
            self.separator
        )

        # -------------------------------------------------
        # Planner Timeline
        # -------------------------------------------------

        self.timeline = QLabel()

        self.timeline.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        self.timeline.setWordWrap(True)

        self.timeline.setText(
            "Waiting..."
        )

        layout.addWidget(
            self.timeline
        )

        # -------------------------------------------------

        self.separator2 = QFrame()

        self.separator2.setFrameShape(
            QFrame.HLine
        )

        layout.addWidget(
            self.separator2
        )

        # -------------------------------------------------
        # Final Response
        # -------------------------------------------------

        self.response = QLabel()

        self.response.setWordWrap(True)

        self.response.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        layout.addWidget(
            self.response)

    # =====================================================
    # Theme
    # =====================================================

    def _apply_theme(self) -> None:

        self.setStyleSheet(
            f"""
            TaskCard {{
                background:{colors.SURFACE};
                border:1px solid {colors.BORDER};
                border-radius:{spacing.PANEL_RADIUS}px;
            }}

            QLabel {{
                color:{colors.TEXT};
                background:transparent;
                font-size:12px;
            }}

            QFrame {{
                color:{colors.BORDER};
                background:{colors.BORDER};
                max-height:1px;
            }}
            """
        )

    # =====================================================
    # Public API
    # =====================================================

    def set_provider(
        self,
        provider: str,
    ) -> None:

        self.provider.setText(
            f"Provider      {provider}"
        )

    # -----------------------------------------------------

    def set_model(
        self,
        model: str,
    ) -> None:

        self.model.setText(
            f"Model         {model}"
        )

    # -----------------------------------------------------

    def set_latency(
        self,
        latency: str,
    ) -> None:

        self.latency.setText(
            f"Latency       {latency}"
        )

    # -----------------------------------------------------

    def set_state(
        self,
        state: TaskState,
    ) -> None:

        self._state = state

        self.state.setText(
            f"Status        {state.value}"
        )

    # -----------------------------------------------------

    def add_step(
        self,
        text: str,
    ) -> None:

        current = self.timeline.text()

        if current == "Waiting...":

            current = ""

        current += f"\n• {text}"

        self.timeline.setText(
            current.strip()
        )

    # -----------------------------------------------------

    def set_response(
        self,
        text: str,
    ) -> None:

        self._response = text

        self.response.setText(
            text
        )

    # -----------------------------------------------------

    def clear_steps(
        self,
    ) -> None:

        self.timeline.setText(
            "Waiting..."
        )