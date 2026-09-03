"""Safety confirmation, shown inside the Home rather than as a modal.

The worker thread is blocked on an event while this is up, so the panel is a
direct replacement for the QMessageBox that used to break the frame. It stays
visually loud on purpose — an approval prompt is the one thing that should
never be softened into the ambient design.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import colors
from ui.theme import typography


class ConfirmPanel(QWidget):

    approved = Signal()
    denied = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        frame = QFrame()
        frame.setObjectName("confirm")
        frame.setMinimumWidth(420)
        frame.setMaximumWidth(560)

        inner = QVBoxLayout(frame)
        inner.setContentsMargins(22, 18, 22, 18)
        inner.setSpacing(12)

        self._title = QLabel("I need your approval")
        self._title.setObjectName("confirm_title")
        inner.addWidget(self._title)

        self._detail = QLabel()
        self._detail.setObjectName("confirm_detail")
        self._detail.setWordWrap(True)
        self._detail.setTextFormat(Qt.PlainText)
        inner.addWidget(self._detail)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()

        self._cancel = QPushButton("Cancel")
        self._cancel.setObjectName("confirm_cancel")
        self._cancel.setCursor(Qt.PointingHandCursor)
        self._cancel.setFixedHeight(32)
        self._cancel.clicked.connect(self.denied.emit)
        buttons.addWidget(self._cancel)

        self._allow = QPushButton("Allow")
        self._allow.setObjectName("confirm_allow")
        self._allow.setCursor(Qt.PointingHandCursor)
        self._allow.setFixedHeight(32)
        self._allow.clicked.connect(self.approved.emit)
        buttons.addWidget(self._allow)

        inner.addLayout(buttons)

        root.addWidget(frame, 0, Qt.AlignHCenter)

        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#confirm {{
                background: {colors.HOME_SURFACE_RAISED};
                border: 1px solid {colors.HOME_ATTENTION};
                border-radius: 14px;
            }}
            QLabel#confirm_title {{
                color: {colors.HOME_ATTENTION};
                font-size: 14px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QLabel#confirm_detail {{
                color: {colors.HOME_TEXT};
                font-size: 13px;
                font-family: "{typography.MONO_FONT}";
                background: transparent;
                border: none;
            }}
            QPushButton#confirm_cancel {{
                background: transparent;
                border: 1px solid {colors.HOME_BORDER_LIT};
                border-radius: 16px;
                color: {colors.HOME_TEXT_SECONDARY};
                font-size: 13px;
                padding: 0 22px;
            }}
            QPushButton#confirm_cancel:hover {{
                color: {colors.HOME_TEXT};
                border-color: {colors.HOME_TEXT_MUTED};
            }}
            QPushButton#confirm_allow {{
                background: {colors.HOME_ATTENTION};
                border: none;
                border-radius: 16px;
                color: #1A1206;
                font-size: 13px;
                font-weight: 600;
                padding: 0 26px;
            }}
            QPushButton#confirm_allow:hover {{
                background: #F0B94E;
            }}
            """
        )

    def ask(self, description: str) -> None:
        self._detail.setText(description)
        self.show()
        self._cancel.setFocus(Qt.OtherFocusReason)
