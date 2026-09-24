"""The navigation rail — Mike's own, not a generic dashboard.

A narrow column: the presence mark and wordmark at the top (the mark shows
Mike's live state, so identity and status are one thing), a set of surfaces
in the middle, and a quiet account slot at the foot for a future sign-in. The
icons are drawn in code — small, geometric, consistent — so the rail reads as
part of one considered product rather than a tray of stock glyphs.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mark import PresenceMark

#: (key, label, icon) in display order.
NAV = [
    ("chat", "Chat", "chat"),
    ("history", "History", "history"),
    ("memory", "Memory", "memory"),
    ("profile", "Profile", "profile"),
    ("settings", "Preferences", "settings"),
    ("voice", "Voice", "voice"),
    ("model", "Model", "model"),
    ("privacy", "Privacy", "privacy"),
    ("about", "About", "about"),
]


def _glyph(p: QPainter, name: str, x: float, y: float, s: float, col: QColor) -> None:
    """Draw a small line icon named `name` in an s×s box at (x, y)."""
    pen = QPen(col)
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    r = QRectF(x, y, s, s)

    if name == "chat":
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y + s * 0.08, s, s * 0.66), 4, 4)
        p.drawPath(path)
        # tail
        p.drawLine(x + s * 0.28, y + s * 0.74, x + s * 0.20, y + s * 0.96)
        p.drawLine(x + s * 0.20, y + s * 0.96, x + s * 0.44, y + s * 0.74)
    elif name == "history":
        p.drawEllipse(r.adjusted(1, 1, -1, -1))
        cx, cy = x + s / 2, y + s / 2
        p.drawLine(cx, cy, cx, cy - s * 0.24)
        p.drawLine(cx, cy, cx + s * 0.18, cy + s * 0.06)
    elif name == "memory":
        # a kept spark — four-point star
        cx, cy = x + s / 2, y + s / 2
        star = QPainterPath()
        star.moveTo(cx, y + s * 0.06)
        star.lineTo(cx + s * 0.14, cy - s * 0.14)
        star.lineTo(x + s * 0.94, cy)
        star.lineTo(cx + s * 0.14, cy + s * 0.14)
        star.lineTo(cx, y + s * 0.94)
        star.lineTo(cx - s * 0.14, cy + s * 0.14)
        star.lineTo(x + s * 0.06, cy)
        star.lineTo(cx - s * 0.14, cy - s * 0.14)
        star.closeSubpath()
        p.drawPath(star)
    elif name == "profile":
        p.drawEllipse(QRectF(x + s * 0.30, y + s * 0.10, s * 0.40, s * 0.40))
        arc = QPainterPath()
        arc.moveTo(x + s * 0.12, y + s * 0.96)
        arc.arcTo(QRectF(x + s * 0.12, y + s * 0.56, s * 0.76, s * 0.80),
                  180, -180)
        p.drawPath(arc)
    elif name == "voice":
        p.drawRoundedRect(QRectF(x + s * 0.36, y + s * 0.10, s * 0.28, s * 0.46),
                          s * 0.14, s * 0.14)
        a = QPainterPath()
        a.moveTo(x + s * 0.24, y + s * 0.44)
        a.arcTo(QRectF(x + s * 0.24, y + s * 0.20, s * 0.52, s * 0.52), 200, 140)
        p.drawPath(a)
        cx = x + s / 2
        p.drawLine(cx, y + s * 0.76, cx, y + s * 0.92)
    elif name == "model":
        p.drawRoundedRect(QRectF(x + s * 0.20, y + s * 0.20, s * 0.60, s * 0.60), 3, 3)
        p.setBrush(col)
        p.drawEllipse(QRectF(x + s * 0.43, y + s * 0.43, s * 0.14, s * 0.14))
        p.setBrush(Qt.NoBrush)
        for t in (0.36, 0.5, 0.64):
            p.drawLine(x + s * t, y + s * 0.20, x + s * t, y + s * 0.10)
            p.drawLine(x + s * t, y + s * 0.80, x + s * t, y + s * 0.90)
            p.drawLine(x + s * 0.20, y + s * t, x + s * 0.10, y + s * t)
            p.drawLine(x + s * 0.80, y + s * t, x + s * 0.90, y + s * t)
    elif name == "privacy":
        shield = QPainterPath()
        shield.moveTo(x + s / 2, y + s * 0.06)
        shield.lineTo(x + s * 0.86, y + s * 0.24)
        shield.lineTo(x + s * 0.86, y + s * 0.54)
        shield.arcTo(QRectF(x + s * 0.14, y + s * 0.30, s * 0.72, s * 0.66), 20, 140)
        shield.lineTo(x + s * 0.14, y + s * 0.24)
        shield.closeSubpath()
        p.drawPath(shield)
    elif name == "settings":
        # three sliders, each a track with a knob at a different position
        for i, (yy, kx) in enumerate([(0.24, 0.66), (0.5, 0.36), (0.76, 0.58)]):
            p.drawLine(x + s * 0.14, y + s * yy, x + s * 0.86, y + s * yy)
            p.setBrush(col)
            p.drawEllipse(QRectF(x + s * kx - s * 0.08, y + s * yy - s * 0.08,
                                 s * 0.16, s * 0.16))
            p.setBrush(Qt.NoBrush)
    elif name == "about":
        p.drawEllipse(r.adjusted(1, 1, -1, -1))
        cx = x + s / 2
        p.setBrush(col)
        p.drawEllipse(QRectF(cx - s * 0.05, y + s * 0.26, s * 0.10, s * 0.10))
        p.setBrush(Qt.NoBrush)
        p.drawLine(cx, y + s * 0.44, cx, y + s * 0.72)


def sidebar_qss() -> str:
    """The rail's stylesheet, rebuilt from the live palette (re-theme safe)."""
    return (
        f"QWidget#sidebar {{ background:{style.GROUND_SUNK}; "
        f"border-right:1px solid {style.HAIRLINE}; }}"
        f"QPushButton#newChat {{ background:{style.GROUND}; color:{style.INK};"
        f" border:1px solid {style.HAIRLINE}; border-radius:10px;"
        f" padding:8px 12px; text-align:left; }}"
        f"QPushButton#newChat:hover {{ border-color:{style.accent()}; }}"
    )


class SidebarItem(QWidget):
    clicked = Signal(str)

    def __init__(self, key: str, label: str, icon: str, parent=None) -> None:
        super().__init__(parent)
        self._key = key
        self._label = label
        self._icon = icon
        self._active = False
        self._hover = False
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def set_active(self, on: bool) -> None:
        if on != self._active:
            self._active = on
            self.update()

    def enterEvent(self, _e):
        self._hover = True
        self.update()

    def leaveEvent(self, _e):
        self._hover = False
        self.update()

    def mousePressEvent(self, _e):
        self.clicked.emit(self._key)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        if self._active:
            bg = QColor(style.accent())
            bg.setAlpha(28)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(8, 3, w - 16, h - 6), 9, 9)
            bar = QColor(style.accent())
            p.setBrush(bar)
            p.drawRoundedRect(QRectF(8, h * 0.28, 3, h * 0.44), 1.5, 1.5)
        elif self._hover:
            bg = QColor(style.INK)
            bg.setAlpha(12)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(8, 3, w - 16, h - 6), 9, 9)

        if self._active:
            col = QColor(style.accent())
            tcol = QColor(style.INK)
        elif self._hover:
            col = QColor(style.INK_SOFT)
            tcol = QColor(style.INK)
        else:
            col = QColor(style.INK_MUTE)
            tcol = QColor(style.INK_SOFT)

        _glyph(p, self._icon, 22, (h - 18) / 2, 18, col)

        p.setPen(tcol)
        f = style.voice(13)
        if self._active:
            f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(QRectF(52, 0, w - 60, h), Qt.AlignVCenter | Qt.AlignLeft, self._label)


class Sidebar(QWidget):
    page_selected = Signal(str)
    new_chat_requested = Signal()

    WIDTH = 212

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(self.WIDTH)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._items: dict[str, SidebarItem] = {}
        self._build()

    def _build(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        # ── identity: the mark + wordmark ──
        top = QWidget()
        top.setStyleSheet("background:transparent;")
        trow = QHBoxLayout(top)
        trow.setContentsMargins(24, 22, 16, 18)
        trow.setSpacing(11)
        self.mark = PresenceMark(26)
        trow.addWidget(self.mark, 0, Qt.AlignVCenter)
        word = QLabel("Mike")
        word.setFont(style.voice(17))
        word.setStyleSheet(
            f"color:{style.INK};background:transparent;font-weight:600;")
        trow.addWidget(word, 1, Qt.AlignVCenter)
        col.addWidget(top)

        # ── a fresh chat: the saved one stays in History ──
        new_wrap = QWidget()
        new_wrap.setStyleSheet("background:transparent;")
        nrow = QHBoxLayout(new_wrap)
        nrow.setContentsMargins(12, 0, 12, 10)
        self._new_chat = QPushButton("+   New chat")
        self._new_chat.setObjectName("newChat")
        self._new_chat.setCursor(Qt.PointingHandCursor)
        self._new_chat.setToolTip("Start a new chat (Ctrl+N)")
        self._new_chat.setFont(style.voice(13))
        self._new_chat.clicked.connect(self.new_chat_requested.emit)
        nrow.addWidget(self._new_chat)
        col.addWidget(new_wrap)

        # ── surfaces ──
        nav = QWidget()
        nav.setStyleSheet("background:transparent;")
        ncol = QVBoxLayout(nav)
        ncol.setContentsMargins(4, 4, 4, 4)
        ncol.setSpacing(2)
        for key, label, icon in NAV:
            item = SidebarItem(key, label, icon)
            item.clicked.connect(self.page_selected.emit)
            self._items[key] = item
            ncol.addWidget(item)
        col.addWidget(nav)

        col.addStretch(1)

        # ── account slot (future-ready, honest about being not-yet) ──
        acct = QWidget()
        acct.setStyleSheet("background:transparent;")
        arow = QVBoxLayout(acct)
        arow.setContentsMargins(20, 10, 16, 18)
        arow.setSpacing(3)
        line = QLabel("Local account")
        line.setFont(style.voice(12))
        line.setStyleSheet(f"color:{style.INK_SOFT};background:transparent;")
        arow.addWidget(line)
        sub = QLabel("Sign-in & sync coming soon")
        sub.setWordWrap(True)
        sub.setFont(style.label(10, QFont.Weight.Normal))
        sub.setStyleSheet(f"color:{style.INK_FAINT};background:transparent;")
        arow.addWidget(sub)
        col.addWidget(acct)

        self.setStyleSheet(sidebar_qss())

    def set_active(self, key: str) -> None:
        for k, item in self._items.items():
            item.set_active(k == key)

    def set_state(self, state: str) -> None:
        self.mark.set_state(state)
