"""Ambient context — where Mike is and whether he's available.

Kept to two short facts on purpose. This is the seam IDE integration will
later feed: set_context("VS Code", "huddle") instead of the frontmost app.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from brain import environment
from ui.theme import colors


class ContextStrip(QWidget):

    # Editor context changes as fast as the user moves between files, and both
    # sources behind this are cheap reads (the frontmost-app lookup has its own
    # 15s cache), so refreshing often costs almost nothing.
    REFRESH_MS = 2500

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(38)

        row = QHBoxLayout(self)
        row.setContentsMargins(22, 0, 22, 0)
        row.setSpacing(10)

        self._dot = QLabel("●")
        self._dot.setObjectName("ctx_dot")
        row.addWidget(self._dot)

        self._name = QLabel("Mike")
        self._name.setObjectName("ctx_name")
        row.addWidget(self._name)

        row.addStretch()

        self._context = QLabel()
        self._context.setObjectName("ctx_detail")
        row.addWidget(self._context)

        self._apply_theme()
        self.set_available(True)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(self.REFRESH_MS)
        self._refresh_timer.timeout.connect(self.refresh_environment)
        self._refresh_timer.start()

        self.refresh_environment()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            ContextStrip {{
                background: transparent;
            }}
            QLabel#ctx_name {{
                color: {colors.HOME_TEXT_SECONDARY};
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.3px;
                background: transparent;
                border: none;
            }}
            QLabel#ctx_detail {{
                color: {colors.HOME_TEXT_MUTED};
                font-size: 12px;
                background: transparent;
                border: none;
            }}
            """
        )

    def set_available(self, available: bool) -> None:
        tone = colors.HOME_SUCCESS if available else colors.HOME_TEXT_MUTED
        self._dot.setStyleSheet(
            f"color: {tone}; font-size: 9px; background: transparent; border: none;"
        )

    def set_context(self, source: str, detail: str = "") -> None:
        """The IDE-integration seam. Today: frontmost app."""

        if not source:
            self._context.setText("")
            return

        self._context.setText(f"{source} · {detail}" if detail else source)

    def refresh_environment(self) -> None:
        """
        Prefers the editor's own view of where the user is when one is
        attached, and falls back to the frontmost app otherwise.
        """

        try:
            from ide import manager

            if manager.is_connected():
                ide_context = manager.get_context()
                detail = " · ".join(
                    part for part in
                    (ide_context.workspace_name, ide_context.filename)
                    if part
                )
                self.set_context(ide_context.editor, detail)
                return

        except Exception:
            pass

        app = environment._frontmost_app()
        self.set_context(app or "")
