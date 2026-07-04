from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
)


class InputBar(QWidget):
    """
    Raycast-inspired command bar.

    Features
    --------
    • Rounded input
    • Enter to send
    • Send button
    • Mic placeholder
    • Image placeholder
    """

    submitted = Signal(str)

    # =====================================================

    def __init__(self) -> None:

        super().__init__()

        self.setFixedHeight(74)

        layout = QHBoxLayout(self)

        layout.setContentsMargins(18, 14, 18, 14)

        layout.setSpacing(10)

        # -------------------------------------------------
        # Input
        # -------------------------------------------------

        self.input = QLineEdit()

        self.input.setPlaceholderText(
            "Instruct Mike to take control..."
        )

        self.input.returnPressed.connect(
            self._submit
        )

        self.input.setStyleSheet(
            """
            QLineEdit{

                background:#09090b;

                border:1px solid #202020;

                border-radius:16px;

                padding:14px;

                color:white;

                font-size:14px;

                selection-background-color:#0ea5e9;
            }

            QLineEdit:focus{

                border:1px solid #0ea5e9;
            }
            """
        )

        # -------------------------------------------------
        # Upload Button
        # -------------------------------------------------

        self.upload = QPushButton("📎")

        self.upload.setFixedSize(42, 42)

        self.upload.setToolTip(
            "Upload image (Coming Soon)"
        )

        # -------------------------------------------------
        # Mic Button
        # -------------------------------------------------

        self.mic = QPushButton("🎤")

        self.mic.setFixedSize(42, 42)

        self.mic.setToolTip(
            "Voice Mode"
        )

        # -------------------------------------------------
        # Send Button
        # -------------------------------------------------

        self.send = QPushButton("➜")

        self.send.setFixedSize(42, 42)

        self.send.clicked.connect(
            self._submit
        )

        # -------------------------------------------------
        # Button Styling
        # -------------------------------------------------

        button_style = """
        QPushButton{

            background:#09090b;

            border:1px solid #202020;

            border-radius:12px;

            color:white;

            font-size:16px;
        }

        QPushButton:hover{

            border:1px solid #0ea5e9;

            background:#101014;
        }

        QPushButton:pressed{

            background:#16161b;
        }
        """

        self.upload.setStyleSheet(button_style)

        self.mic.setStyleSheet(button_style)

        self.send.setStyleSheet(button_style)

        # -------------------------------------------------

        layout.addWidget(self.input)

        layout.addWidget(self.upload)

        layout.addWidget(self.mic)

        layout.addWidget(self.send)

    # =====================================================

    def _submit(self) -> None:

        text = self.input.text().strip()

        if not text:

            return

        self.submitted.emit(text)

        self.input.clear()

    # =====================================================

    def focus(self) -> None:

        self.input.setFocus()

    # =====================================================

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:

        self.input.setEnabled(enabled)

        self.send.setEnabled(enabled)

        self.upload.setEnabled(enabled)

        self.mic.setEnabled(enabled)