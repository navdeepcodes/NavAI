"""What Mike can actually do.

Built at runtime from the real tool declarations, so this surface cannot drift
from reality: remove a tool from the brain and its entry disappears here, add
one and it shows up (under "Other" until it's given a home).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from brain.core_tools import TOOL_DECLARATIONS
from ui.theme import colors


# function name -> (group, human label). Groups render in this order.
_GROUPS = ("THINK", "SEE", "ACT", "SPEAK", "WORK")

_TOOL_MAP = {
    "remember": ("THINK", "Remember facts"),
    "recall_memory": ("THINK", "Recall what it knows"),
    "forget_memory": ("THINK", "Forget on request"),

    "see_screen": ("SEE", "Look at your screen"),
    "read_document": ("SEE", "Read PDF, DOCX, PPTX, CSV"),
    "read_file": ("SEE", "Read files"),
    "list_directory": ("SEE", "Browse folders"),

    "open_browser": ("ACT", "Open the browser"),
    "open_url": ("ACT", "Open any link"),
    "search_web": ("ACT", "Search the web"),
    "create_folder": ("ACT", "Create folders"),
    "create_file": ("ACT", "Create files"),
    "write_file": ("ACT", "Write to files"),
    "delete_path": ("ACT", "Delete files (asks first)"),
    "run_command": ("ACT", "Run terminal commands (asks first)"),

    "search_files": ("WORK", "Search inside your code"),
}

# Real capabilities that aren't tool calls. Each one is backed by shipped code.
_INTRINSIC = (
    ("THINK", "Multi-step tasks"),
    ("THINK", "Remembers the conversation"),
    ("SPEAK", "Voice input"),
    ("SPEAK", "Speaks back"),
    ("SPEAK", "Wake word — “Hey Mike”"),
    ("WORK", "Runs fully on this Mac"),
)


def build_capability_map() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {g: [] for g in _GROUPS}
    grouped["Other"] = []

    for decl in TOOL_DECLARATIONS:
        group, label = _TOOL_MAP.get(decl.name, ("Other", decl.name))
        grouped.setdefault(group, []).append(label)

    for group, label in _INTRINSIC:
        grouped.setdefault(group, []).append(label)

    return {g: items for g, items in grouped.items() if items}


class CapabilitiesOverlay(QWidget):
    """Layer 5 — hidden until asked for."""

    dismissed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("cap_panel")

        inner = QVBoxLayout(panel)
        inner.setContentsMargins(30, 24, 30, 24)
        inner.setSpacing(18)

        heading = QLabel("What Mike can do")
        heading.setObjectName("cap_heading")
        inner.addWidget(heading)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(38)
        grid.setVerticalSpacing(20)

        capability_map = build_capability_map()
        for index, (group, items) in enumerate(capability_map.items()):
            column = QVBoxLayout()
            column.setSpacing(7)

            title = QLabel(group)
            title.setObjectName("cap_group")
            column.addWidget(title)

            for item in items:
                entry = QLabel(item)
                entry.setObjectName("cap_item")
                column.addWidget(entry)

            column.addStretch()

            host = QWidget()
            host.setLayout(column)
            grid.addWidget(host, index // 3, index % 3, Qt.AlignTop)

        grid.setRowStretch(grid.rowCount(), 1)

        inner.addWidget(grid_host)
        inner.addStretch()

        close = QPushButton("Close")
        close.setObjectName("cap_close")
        close.setCursor(Qt.PointingHandCursor)
        close.setFixedHeight(30)
        close.clicked.connect(self.dismissed.emit)
        inner.addWidget(close, 0, Qt.AlignHCenter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(panel)

        # The viewport paints its own background by default and would come out
        # white regardless of the stylesheet above it.
        scroll.viewport().setAutoFillBackground(False)
        panel.setAutoFillBackground(False)

        root.addWidget(scroll)

        self.setAutoFillBackground(True)

        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            CapabilitiesOverlay {{
                background: {colors.HOME_GROUND};
            }}
            QScrollArea {{
                background: {colors.HOME_GROUND};
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background: {colors.HOME_GROUND};
            }}
            QFrame#cap_panel {{
                background: {colors.HOME_GROUND};
            }}
            QLabel#cap_heading {{
                color: {colors.HOME_TEXT};
                font-size: 19px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QLabel#cap_group {{
                color: {colors.HOME_ACCENT};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1.4px;
                background: transparent;
                border: none;
            }}
            QLabel#cap_item {{
                color: {colors.HOME_TEXT_SECONDARY};
                font-size: 13px;
                background: transparent;
                border: none;
            }}
            QPushButton#cap_close {{
                background: transparent;
                border: 1px solid {colors.HOME_BORDER_LIT};
                border-radius: 15px;
                color: {colors.HOME_TEXT_SECONDARY};
                font-size: 12px;
                padding: 0 24px;
            }}
            QPushButton#cap_close:hover {{
                color: {colors.HOME_TEXT};
                border-color: {colors.HOME_ACCENT};
            }}
            """
        )

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.dismissed.emit()
            return
        super().keyPressEvent(event)
