"""Reading the Privacy Policy, Terms and licences inside Mike.

A calm reading window in Mike's own type — not a web page, not a text dump —
opened from Settings → About and from the first-run consent.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)

from ui.panel import style


class LegalDialog(QDialog):

    def __init__(self, key: str, parent=None) -> None:
        super().__init__(parent)
        from brain import legal
        from ui.panel import richtext

        self.setWindowTitle(f"{legal.title(key)} — Mike")
        self.resize(760, 680)
        self.setStyleSheet(f"QDialog{{background:{style.GROUND};}}")
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setFrameShape(QFrame.NoFrame)
        view.setStyleSheet(
            f"QTextBrowser{{background:{style.GROUND};border:none;padding:28px 40px;"
            f"color:{style.INK};}}"
            f"QScrollBar:vertical{{background:transparent;width:9px;margin:6px 3px;}}"
            f"QScrollBar::handle:vertical{{background:{style.INK_FAINT};border-radius:4px;}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}")
        html, _codes = richtext.render(legal.load(key))
        view.setHtml(html)
        col.addWidget(view, 1)

        foot = QFrame()
        foot.setStyleSheet(f"QFrame{{background:{style.GROUND_RAISED};"
                           f"border-top:1px solid {style.HAIRLINE};}}")
        row = QHBoxLayout(foot)
        row.setContentsMargins(20, 12, 20, 12)
        note = QLabel("A copy ships with Mike, so this is always the version you agreed to.")
        note.setFont(style.font(style.CAPTION))
        note.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;border:none;")
        row.addWidget(note, 1)
        close = QPushButton("Close")
        close.setCursor(Qt.PointingHandCursor)
        close.setFont(style.font(style.SMALL, QFont.Weight.DemiBold))
        close.setStyleSheet(
            f"QPushButton{{background:{style.INK};color:{style.GROUND};border:none;"
            f"border-radius:9px;padding:8px 18px;}}")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        col.addWidget(foot)


def show(key: str, parent=None) -> None:
    LegalDialog(key, parent).exec()
