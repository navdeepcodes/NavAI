from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.theme import colors
from ui.theme import typography


SUGGESTIONS = [
    ("Open YouTube", "Open youtube.com"),
    ("Create a folder on my Desktop", "Create a folder on my Desktop"),
    ("Search the web for today's news", "Search the web for today's news"),
]


class SuggestionButton(QPushButton):

    def __init__(self, text: str) -> None:

        super().__init__(text)

        self.setCursor(Qt.PointingHandCursor)

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        self.setFixedHeight(48)

        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {colors.SURFACE};
                border: 1px solid {colors.BORDER};
                border-radius: 12px;
                color: {colors.TEXT_SECONDARY};
                font-size: {typography.BODY}px;
                padding: 0 20px;
                text-align: left;
            }}

            QPushButton:hover {{
                background: {colors.SURFACE_ELEVATED};
                border-color: {colors.BORDER_STRONG};
                color: {colors.TEXT};
            }}

            QPushButton:pressed {{
                background: {colors.SURFACE_ACTIVE};
            }}
            """
        )


class WelcomePanel(QWidget):

    suggestion_clicked = Signal(str)

    MAX_WIDTH = 460

    def __init__(self) -> None:

        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addStretch(3)

        # Center container
        center = QWidget()
        center.setMaximumWidth(self.MAX_WIDTH)

        container = QVBoxLayout(center)
        container.setContentsMargins(20, 0, 20, 0)
        container.setSpacing(0)

        # Title
        title = QLabel("Mike")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"""
            color: {colors.TEXT};
            font-size: 32px;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: transparent;
            """
        )
        container.addWidget(title)

        container.addSpacing(8)

        # Subtitle
        subtitle = QLabel("Your computer, at your command.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"""
            color: {colors.TEXT_MUTED};
            font-size: {typography.SUBTITLE}px;
            background: transparent;
            """
        )
        container.addWidget(subtitle)

        container.addSpacing(40)

        # Suggestions
        for label, command in SUGGESTIONS:
            btn = SuggestionButton(label)
            btn.clicked.connect(
                lambda checked, c=command: self.suggestion_clicked.emit(c)
            )
            container.addWidget(btn)
            container.addSpacing(8)

        # Horizontal centering
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch()
        h.addWidget(center)
        h.addStretch()

        outer.addLayout(h)
        outer.addStretch(4)
