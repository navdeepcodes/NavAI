from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from ui.theme import colors
from ui.theme import typography


def _parse_action(text: str) -> tuple[str, str, str]:
    """Parse friendly_tool_name output into (icon, label, detail)."""

    t = text.strip()

    if t.startswith("Opening http") or t.startswith("Opening www"):
        url = t.replace("Opening ", "", 1)
        domain = url.split("//")[-1].split("/")[0].split("?")[0]
        return "◎", "Opening URL", domain

    if t.startswith("Opening browser"):
        return "◎", "Opening browser", ""

    if t.startswith("Searching for "):
        query = t.replace("Searching for ", "", 1)
        return "◎", "Searching the web", query

    if t.startswith("Creating folder "):
        path = t.replace("Creating folder ", "", 1)
        return "□", "Creating folder", _short_path(path)

    if t.startswith("Creating file "):
        path = t.replace("Creating file ", "", 1)
        return "□", "Creating file", _short_path(path)

    if t.startswith("Reading "):
        path = t.replace("Reading ", "", 1)
        return "□", "Reading file", _short_path(path)

    if t.startswith("Writing to "):
        path = t.replace("Writing to ", "", 1)
        return "□", "Writing file", _short_path(path)

    if t.startswith("Listing "):
        path = t.replace("Listing ", "", 1)
        return "□", "Listing directory", _short_path(path)

    if t.startswith("Deleting "):
        path = t.replace("Deleting ", "", 1)
        return "□", "Deleting", _short_path(path)

    if t.startswith("Running: "):
        cmd = t.replace("Running: ", "", 1)
        return "❯", "Running command", cmd

    if t.startswith("Reading document "):
        path = t.replace("Reading document ", "", 1)
        return "▤", "Reading document", _short_path(path)

    if t.startswith("Searching for "):
        query = t.replace("Searching for ", "", 1)
        if not query.startswith("http"):
            return "⊕", "Searching files", query

    if t == "Looking at your screen":
        return "◉", "Looking at your screen", ""

    return "•", t, ""


def _short_path(path: str) -> str:
    if len(path) > 55:
        parts = path.split("/")
        if len(parts) > 3:
            return parts[0] + "/…/" + "/".join(parts[-2:])
    return path


class ToolBubble(QFrame):

    MAX_WIDTH = 440

    def __init__(self, text: str) -> None:

        super().__init__()

        self.setObjectName("action_card")

        self.setMaximumWidth(self.MAX_WIDTH)
        self.setMinimumWidth(240)

        self.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Fixed,
        )

        icon, label, detail = _parse_action(text)

        self._build_ui(icon, label, detail)

        self._apply_theme()

        self._completed = False

    def _build_ui(
        self,
        icon: str,
        label: str,
        detail: str,
    ) -> None:

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # Icon
        self._icon = QLabel(icon)
        self._icon.setObjectName("action_icon")
        self._icon.setAlignment(Qt.AlignTop)
        self._icon.setFixedWidth(20)

        layout.addWidget(self._icon)

        # Text column
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)

        self._label = QLabel(label)
        self._label.setObjectName("action_label")

        text_col.addWidget(self._label)

        if detail:
            self._detail = QLabel(detail)
            self._detail.setObjectName("action_detail")
            self._detail.setWordWrap(True)
            text_col.addWidget(self._detail)
        else:
            self._detail = None

        layout.addLayout(text_col, 1)

        # Status
        self._status = QLabel("•••")
        self._status.setObjectName("action_status")
        self._status.setAlignment(
            Qt.AlignRight | Qt.AlignVCenter
        )
        self._status.setFixedWidth(28)

        layout.addWidget(self._status)

    def _apply_theme(self) -> None:

        self.setStyleSheet(
            f"""
            QFrame#action_card {{
                background: {colors.SURFACE};
                border: 1px solid {colors.BORDER};
                border-radius: 12px;
            }}

            QLabel#action_icon {{
                color: {colors.ACCENT};
                font-size: 15px;
                background: transparent;
                border: none;
                padding-top: 1px;
            }}

            QLabel#action_label {{
                color: {colors.TEXT};
                font-size: {typography.SMALL}px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}

            QLabel#action_detail {{
                color: {colors.TEXT_MUTED};
                font-size: {typography.TINY}px;
                font-family: "{typography.MONO_FONT}";
                background: transparent;
                border: none;
            }}

            QLabel#action_status {{
                color: {colors.TEXT_DISABLED};
                font-size: 13px;
                background: transparent;
                border: none;
            }}
            """
        )

    def mark_done(self, success: bool = True) -> None:

        if self._completed:
            return

        self._completed = True

        if success:
            self._status.setText("✓")
            self._status.setStyleSheet(
                f"color: {colors.SUCCESS}; font-size: 16px; font-weight: 700;"
                " background: transparent; border: none;"
            )
            self.setStyleSheet(
                f"""
                QFrame#action_card {{
                    background: {colors.SURFACE};
                    border: 1px solid #1A3028;
                    border-radius: 12px;
                }}
                QLabel#action_icon {{
                    color: {colors.SUCCESS};
                    font-size: 15px;
                    background: transparent; border: none;
                    padding-top: 1px;
                }}
                QLabel#action_label {{
                    color: {colors.TEXT};
                    font-size: {typography.SMALL}px;
                    font-weight: 600;
                    background: transparent; border: none;
                }}
                QLabel#action_detail {{
                    color: {colors.TEXT_MUTED};
                    font-size: {typography.TINY}px;
                    font-family: "{typography.MONO_FONT}";
                    background: transparent; border: none;
                }}
                QLabel#action_status {{
                    color: {colors.SUCCESS};
                    font-size: 16px; font-weight: 700;
                    background: transparent; border: none;
                }}
                """
            )
        else:
            self._status.setText("✗")
            self._status.setStyleSheet(
                f"color: {colors.ERROR}; font-size: 16px; font-weight: 700;"
                " background: transparent; border: none;"
            )
            self.setStyleSheet(
                f"""
                QFrame#action_card {{
                    background: {colors.SURFACE};
                    border: 1px solid #3A1A1A;
                    border-radius: 12px;
                }}
                QLabel#action_icon {{
                    color: {colors.ERROR};
                    font-size: 15px;
                    background: transparent; border: none;
                    padding-top: 1px;
                }}
                QLabel#action_label {{
                    color: {colors.TEXT};
                    font-size: {typography.SMALL}px;
                    font-weight: 600;
                    background: transparent; border: none;
                }}
                QLabel#action_detail {{
                    color: {colors.TEXT_MUTED};
                    font-size: {typography.TINY}px;
                    font-family: "{typography.MONO_FONT}";
                    background: transparent; border: none;
                }}
                QLabel#action_status {{
                    color: {colors.ERROR};
                    font-size: 16px; font-weight: 700;
                    background: transparent; border: none;
                }}
                """
            )

    # BubbleBase compatibility

    def set_text(self, text: str) -> None:
        self._label.setText(text)

    def append_text(self, text: str) -> None:
        self._label.setText(self._label.text() + text)

    def text(self) -> str:
        return self._label.text()
