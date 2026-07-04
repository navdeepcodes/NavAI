from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
)

from ui.theme import colors


class StatusBar(QFrame):
    """
    Bottom runtime status bar.

    Responsibilities
    ----------------
    • Display runtime status
    • Display active provider
    • Display lightweight activity
    """

    BAR_HEIGHT = 32

    # =====================================================

    def __init__(self) -> None:

        super().__init__()

        self._build_ui()

        self._apply_theme()

    # =====================================================

    def _build_ui(self) -> None:

        layout = QHBoxLayout(self)

        layout.setContentsMargins(
            16,
            8,
            16,
            8,
        )

        layout.setSpacing(12)

        self.status = QLabel("Ready")

        self.provider = QLabel("")

        self.status.setAlignment(Qt.AlignLeft)

        self.provider.setAlignment(Qt.AlignRight)

        layout.addWidget(self.status)

        layout.addStretch()

        layout.addWidget(self.provider)

    # =====================================================

    def _apply_theme(self) -> None:

        self.setFixedHeight(self.BAR_HEIGHT)

        self.setStyleSheet(
            f"""
            StatusBar {{
                background:{colors.SURFACE};
                border-top:1px solid {colors.BORDER};
            }}

            QLabel {{
                color:{colors.TEXT_MUTED};
                background:transparent;
                font-size:11px;
            }}
            """
        )

    # =====================================================
    # Public API
    # =====================================================

    def set_text(
        self,
        text: str,
    ) -> None:

        self.status.setText(text)

    # -----------------------------------------------------

    def set_provider(
        self,
        provider: str,
    ) -> None:

        self.provider.setText(provider)

    # -----------------------------------------------------

    def clear_provider(self) -> None:

        self.provider.clear()

    # -----------------------------------------------------

    def set_runtime(
        self,
        *,
        status: str | None = None,
        provider: str | None = None,
    ) -> None:

        if status is not None:

            self.set_text(status)

        if provider is not None:

            self.set_provider(provider)

    # -----------------------------------------------------

    def ready(self) -> None:

        self.set_text("Ready")

    # -----------------------------------------------------

    def busy(self) -> None:

        self.set_text("Thinking...")

    # -----------------------------------------------------

    def error(self) -> None:

        self.set_text("Runtime Error")

    # -----------------------------------------------------

    def clear(self) -> None:

        self.ready()

        self.clear_provider()