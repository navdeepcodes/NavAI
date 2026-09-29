"""The rail — your conversations with Mike, and nothing else.

Deliberately quiet: Mike's mark and name at the top (the mark carries his live
state, so identity and status are one thing), a way to start a new chat, and
then the chats themselves — click one to carry on where you left off. Every
other surface (profile, appearance, voice, memory, activity, privacy) lives in
Settings, reached from the profile row at the foot, so the rail never turns
into a dashboard.

The whole rail folds away (the toggle at its top, or Ctrl+B) when you want the
conversation to have the room.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mark import PresenceMark
from ui.workspace.icons import IconButton, draw


def sidebar_qss() -> str:
    """The rail's stylesheet, rebuilt from the live palette (re-theme safe)."""
    # The rail's own fill is painted (Sidebar.paintEvent) so it can follow the
    # window's rounded corners; the stylesheet only styles what's inside it.
    return (
        f"QScrollArea#recents {{ background:transparent; border:none; }}"
        f"QScrollBar:vertical {{ background:transparent; width:8px; margin:2px; }}"
        f"QScrollBar::handle:vertical {{ background:{style.INK_FAINT};"
        f" border-radius:3px; min-height:28px; }}"
        f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
        f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}"
        f"QPushButton#rowDelete {{ background:transparent; border:none; }}"
        f"QPushButton#rowDelete[armed=\"true\"] {{ background:{style.STOP}; color:#FFFFFF;"
        f" border-radius:7px; padding:2px 9px; font-weight:600; }}"
    )


class _RailItem(QWidget):
    """A top-of-rail action (New chat): an icon, a label, a quiet shortcut."""

    clicked = Signal()

    def __init__(self, icon: str, label: str, hint: str = "", parent=None) -> None:
        super().__init__(parent)
        self._icon, self._label, self._hint = icon, label, hint
        self._hover = False
        self.setFixedHeight(38)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(label)

    def enterEvent(self, _e):
        self._hover = True
        self.update()

    def leaveEvent(self, _e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if self._hover:
            tile = QColor(style.INK)
            tile.setAlpha(14)
            p.setPen(Qt.NoPen)
            p.setBrush(tile)
            p.drawRoundedRect(QRectF(8, 2, w - 16, h - 4), 9, 9)
        # the icon sits in a small disc, like a button within the row
        disc = QColor(style.INK)
        disc.setAlpha(22 if self._hover else 14)
        p.setPen(Qt.NoPen)
        p.setBrush(disc)
        p.drawEllipse(QRectF(18, (h - 24) / 2, 24, 24))
        draw(p, self._icon, QRectF(22, (h - 16) / 2, 16, 16), QColor(style.INK), 1.7)
        p.setPen(QColor(style.INK))
        p.setFont(style.font(style.BODY, QFont.Weight.Medium))
        p.drawText(QRectF(52, 0, w - 60, h), Qt.AlignVCenter | Qt.AlignLeft, self._label)
        if self._hint and self._hover:
            p.setPen(QColor(style.INK_MUTE))
            p.setFont(style.font(style.CAPTION))
            p.drawText(QRectF(0, 0, w - 20, h), Qt.AlignVCenter | Qt.AlignRight, self._hint)


class _DeleteButton(QPushButton):
    """Deleting a chat takes two clicks.

    The first click only asks ("Delete?", in red); a second click within three
    seconds deletes, otherwise it quietly reverts. One stray click must never
    permanently erase a conversation.
    """

    confirmed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("", parent)
        self.setObjectName("rowDelete")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip("Delete this chat")
        self.setFont(style.font(style.CAPTION, QFont.Weight.DemiBold))
        self.setProperty("armed", False)
        self.setFixedSize(26, 26)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._revert)
        self.clicked.connect(self._on_click)

    @property
    def armed(self) -> bool:
        return bool(self.property("armed"))

    def _set_armed(self, on: bool) -> None:
        self.setProperty("armed", on)
        self.setText("Delete?" if on else "")
        if on:
            self.setFixedSize(self.fontMetrics().horizontalAdvance("Delete?") + 22, 24)
        else:
            self.setFixedSize(26, 26)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _on_click(self) -> None:
        if self.armed:
            self._timer.stop()
            self._set_armed(False)
            self.confirmed.emit()
            return
        self._set_armed(True)
        self._timer.start(3000)

    def _revert(self) -> None:
        self._set_armed(False)

    def paintEvent(self, e) -> None:
        if self.armed:
            super().paintEvent(e)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        hover = self.underMouse()
        if hover:
            tile = QColor(style.INK)
            tile.setAlpha(18)
            p.setPen(Qt.NoPen)
            p.setBrush(tile)
            p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 7, 7)
        col = QColor(style.STOP if hover else style.INK_MUTE)
        draw(p, "trash", QRectF(5, 5, self.width() - 10, self.height() - 10), col, 1.5)


class ConversationRow(QWidget):
    """One saved chat in the rail: click to reopen it, the bin to delete it."""

    opened = Signal(int)
    deleted = Signal(int)

    HEIGHT = 36

    def __init__(self, convo: dict, current: bool, parent=None) -> None:
        super().__init__(parent)
        self._id = int(convo["id"])
        self._title = (convo.get("title") or "").strip() or "Untitled chat"
        self._current = current
        self._hover = False
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self._title)
        self.setAccessibleName(self._title)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 14, 0)
        row.addStretch(1)
        self._delete = _DeleteButton(self)
        self._delete.confirmed.connect(lambda: self.deleted.emit(self._id))
        self._delete.setVisible(False)
        row.addWidget(self._delete, 0, Qt.AlignVCenter)

    @property
    def conversation_id(self) -> int:
        return self._id

    @property
    def delete_button(self) -> _DeleteButton:
        return self._delete

    def set_current(self, on: bool) -> None:
        if on != self._current:
            self._current = on
            self.update()

    def enterEvent(self, _e):
        self._hover = True
        self._delete.setVisible(True)
        self.update()

    def leaveEvent(self, _e):
        self._hover = False
        # stay visible while it's asking "Delete?", so the second click lands
        if not self._delete.armed:
            self._delete.setVisible(False)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.opened.emit(self._id)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if self._current or self._hover:
            tile = QColor(style.INK)
            tile.setAlpha(24 if self._current else 12)
            p.setPen(Qt.NoPen)
            p.setBrush(tile)
            p.drawRoundedRect(QRectF(8, 1, w - 16, h - 2), 9, 9)

        # a small marker: filled for the chat you're in, a ring otherwise
        cy = h / 2
        if self._current:
            p.setPen(Qt.NoPen)
            p.setBrush(style.qaccent())
            p.drawEllipse(QRectF(24, cy - 3.5, 7, 7))
        else:
            ring = QColor(style.INK_MUTE)
            ring.setAlpha(150)
            pen = p.pen()
            pen.setColor(ring)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(24.5, cy - 3, 6, 6))

        right = w - 22 - (self._delete.width() + 6 if self._delete.isVisible() else 0)
        f = style.font(style.BODY, QFont.Weight.Medium if self._current else QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor(style.INK if (self._current or self._hover) else style.INK_SOFT))
        text = p.fontMetrics().elidedText(self._title, Qt.ElideRight, int(right - 44))
        p.drawText(QRectF(44, 0, right - 44, h), Qt.AlignVCenter | Qt.AlignLeft, text)


class _ProfileRow(QWidget):
    """The foot of the rail: who Mike is working for, and the way into Settings."""

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._name = ""
        self._photo = None
        self._subtitle = ""
        self._hover = False
        self.setFixedHeight(56)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Settings")
        self.setAccessibleName("Settings")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 14, 0)
        row.addStretch(1)
        self.gear = IconButton("gear", "Settings", size=32, icon_size=18)
        self.gear.clicked.connect(self.clicked.emit)
        row.addWidget(self.gear, 0, Qt.AlignVCenter)
        self.refresh()

    def refresh(self) -> None:
        from ui.workspace import avatar
        self._name, self._photo = avatar.current()
        self._subtitle = ""
        try:
            from account.manager import manager
            m = manager()
            if m.signed_in():
                self._subtitle = "Offline" if m.offline else m.email()
        except Exception:
            pass
        self.update()

    def enterEvent(self, _e):
        self._hover = True
        self.update()

    def leaveEvent(self, _e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if self._hover:
            tile = QColor(style.INK)
            tile.setAlpha(12)
            p.setPen(Qt.NoPen)
            p.setBrush(tile)
            p.drawRoundedRect(QRectF(8, 6, w - 16, h - 12), 10, 10)
        # avatar: your photo when signed in with one, else the initial of the
        # name you gave Mike, on the accent
        from ui.workspace import avatar
        d = 30
        ay = (h - d) / 2
        avatar.paint(p, QRectF(18, ay, d, d), self._name, self._photo)

        p.setPen(QColor(style.INK))
        p.setFont(style.font(style.BODY, QFont.Weight.Medium))
        name = self._name or "You"
        fm = p.fontMetrics()
        name = fm.elidedText(name, Qt.ElideRight, w - 58 - 56)
        p.drawText(QRectF(58, h / 2 - 17, w - 110, 18), Qt.AlignLeft | Qt.AlignBottom, name)
        p.setPen(QColor(style.INK_MUTE))
        p.setFont(style.font(style.CAPTION))
        from ui.panel.mike_panel import _this_machine
        subtitle = self._subtitle or f"Private · on {_this_machine()}"
        subtitle = p.fontMetrics().elidedText(subtitle, Qt.ElideRight, w - 58 - 56)
        p.drawText(QRectF(58, h / 2 + 1, w - 110, 16), Qt.AlignLeft | Qt.AlignTop, subtitle)


class Sidebar(QWidget):
    new_chat_requested = Signal()
    conversation_opened = Signal(int)
    conversation_deleted = Signal(int)
    settings_requested = Signal()
    collapse_requested = Signal()

    WIDTH = 264
    TOP_H = 52

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(0)
        self.setMaximumWidth(self.WIDTH)
        self._rows: dict[int, ConversationRow] = {}
        self._current: int | None = None
        self._build()

    def _build(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        # Everything sits in a fixed-width inner column, so folding the rail
        # (animating its width to 0) slides it away rather than reflowing it.
        inner = QWidget()
        inner.setObjectName("sidebarInner")
        inner.setFixedWidth(self.WIDTH)
        inner.setStyleSheet("QWidget#sidebarInner{background:transparent;}")
        icol = QVBoxLayout(inner)
        icol.setContentsMargins(0, 0, 0, 0)
        icol.setSpacing(0)
        col.addWidget(inner, 1, Qt.AlignLeft)

        # ── identity + fold ──
        top = QWidget()
        top.setObjectName("sidebarTop")
        top.setFixedHeight(self.TOP_H)
        trow = QHBoxLayout(top)
        trow.setContentsMargins(20, 0, 12, 0)
        trow.setSpacing(10)
        self.mark = PresenceMark(24)
        trow.addWidget(self.mark, 0, Qt.AlignVCenter)
        word = QLabel("Mike")
        word.setObjectName("wordmark")
        word.setFont(style.font(17, QFont.Weight.DemiBold))
        word.setStyleSheet(f"color:{style.INK};background:transparent;")
        trow.addWidget(word, 1, Qt.AlignVCenter)
        self.fold = IconButton("sidebar", "Hide sidebar (Ctrl+B)", size=32, icon_size=18)
        self.fold.clicked.connect(self.collapse_requested.emit)
        trow.addWidget(self.fold, 0, Qt.AlignVCenter)
        icol.addWidget(top)

        # ── a fresh chat: the one you were in stays below ──
        icol.addSpacing(4)
        self._new_chat = _RailItem("plus", "New chat", "Ctrl+N")
        self._new_chat.setToolTip("Start a new chat (Ctrl+N)")
        self._new_chat.clicked.connect(self.new_chat_requested.emit)
        icol.addWidget(self._new_chat)

        # ── recents ──
        icol.addSpacing(18)
        head = QLabel("Recents")
        head.setFont(style.font(style.CAPTION, QFont.Weight.Medium))
        head.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;padding-left:22px;")
        icol.addWidget(head)
        icol.addSpacing(6)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("recents")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self._list = QVBoxLayout(holder)
        self._list.setContentsMargins(0, 0, 0, 8)
        self._list.setSpacing(1)
        self._list.addStretch(1)
        self._scroll.setWidget(holder)
        icol.addWidget(self._scroll, 1)

        self._empty = QLabel("Your chats will appear here.")
        self._empty.setFont(style.font(style.SMALL))
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet(
            f"color:{style.INK_MUTE};background:transparent;padding:4px 22px;")
        self._list.insertWidget(0, self._empty)

        # ── the foot: you, and Settings ──
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background:{style.HAIRLINE};border:none;")
        icol.addWidget(rule)
        self.profile = _ProfileRow()
        self.profile.clicked.connect(self.settings_requested.emit)
        icol.addWidget(self.profile)
        icol.addSpacing(4)

        self.setStyleSheet(sidebar_qss())

    # ── conversations ─────────────────────────────────────
    def set_conversations(self, convos: list[dict], current: int | None) -> None:
        """Show the saved chats, newest first, marking the one you're in."""
        self._current = current
        for row in self._rows.values():
            row.hide()
            self._list.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        for i, c in enumerate(convos):
            row = ConversationRow(c, current is not None and int(c["id"]) == int(current))
            row.opened.connect(self.conversation_opened.emit)
            row.deleted.connect(self.conversation_deleted.emit)
            self._list.insertWidget(i, row)
            self._rows[int(c["id"])] = row
        self._empty.setVisible(not convos)

    def set_current(self, conversation_id: int | None) -> None:
        self._current = conversation_id
        for cid, row in self._rows.items():
            row.set_current(conversation_id is not None and cid == int(conversation_id))

    def rows(self) -> list[ConversationRow]:
        return list(self._rows.values())

    # ── state / profile ───────────────────────────────────
    def set_state(self, state: str) -> None:
        self.mark.set_state(state)

    def refresh_profile(self) -> None:
        self.profile.refresh()

    # ── the rail's material ───────────────────────────────
    _rounded = True

    def set_rounded(self, on: bool) -> None:
        """Follow the window: rounded outer corners, square when maximised."""
        self._rounded = on
        self.update()

    def paintEvent(self, _e) -> None:
        from PySide6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        r = 12.0 if self._rounded else 0.0
        path = QPainterPath()
        path.moveTo(w, 0)
        path.lineTo(r, 0)
        path.quadTo(0, 0, 0, r)
        path.lineTo(0, h - r)
        path.quadTo(0, h, r, h)
        path.lineTo(w, h)
        path.closeSubpath()
        p.fillPath(path, QColor(style.GROUND_SUNK))
        p.fillRect(QRectF(w - 1, 0, 1, h), QColor(style.HAIRLINE))
