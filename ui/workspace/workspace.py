"""FULL MIKE — the desktop workspace.

A real application window: a slim titlebar with the window controls, a
navigation rail down the left, and a stack of surfaces on the right with the
conversation as the first and default one. It re-exposes exactly the contract
UIController speaks (input / conversation / confirm / activity and the
add_* / begin_* / set_state / *_requested surface) by delegating the
conversation calls to the chat page, so the engine underneath is untouched —
the window is a new shell around the same Mike.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.workspace.chat_page import ChatPage
from ui.workspace.sidebar import Sidebar
from ui.workspace import pages as P


class MikeWorkspace(QWidget):

    # the controller listens for state; the window for the chrome actions
    state_changed = Signal(str)
    dismiss_requested = Signal()
    minimise_requested = Signal()
    maximise_requested = Signal()

    TITLE_H = 44

    def __init__(self, settings_hooks: dict | None = None) -> None:
        super().__init__()
        self._hooks = settings_hooks or {}
        self._maximised = False
        self._build()

    # ── construction ──────────────────────────────────────
    def _build(self) -> None:
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._titlebar())

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        crow = QHBoxLayout(content)
        crow.setContentsMargins(0, 0, 0, 0)
        crow.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.page_selected.connect(self._select)
        crow.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background:transparent;")
        crow.addWidget(self.stack, 1)

        root.addWidget(content, 1)

        # ── the pages ──
        self.chat = ChatPage()
        self.chat.state_changed.connect(self._on_state)
        self._pages: dict[str, QWidget] = {"chat": self.chat}
        self.stack.addWidget(self.chat)

        # secondary surfaces are built lazily but registered here by key
        self._page_factories = {
            "history": P.HistoryPage,
            "memory": P.MemoryPage,
            "profile": P.ProfilePage,
            "settings": P.PreferencesPage,
            "voice": lambda: P.VoicePage(self._hooks),
            "model": P.ModelPage,
            "privacy": P.PrivacyPage,
            "about": P.AboutPage,
        }

        # ── the controller contract: delegate conversation to the chat page ──
        self.input = self.chat.input
        self.conversation = self.chat.conversation
        self.confirm = self.chat.confirm
        self.activity = self.chat.activity

        self.sidebar.set_active("chat")
        self.setStyleSheet(self._qss())

    def _titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titlebar")
        bar.setFixedHeight(self.TITLE_H)
        bar.setAttribute(Qt.WA_StyledBackground, True)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 0, 12, 0)
        row.setSpacing(6)
        row.addStretch(1)

        self._min = QPushButton("–")
        self._min.setObjectName("winbtn")
        self._min.setToolTip("Minimise to the corner")
        self._min.clicked.connect(self.minimise_requested.emit)

        self._max = QPushButton("▢")
        self._max.setObjectName("winbtn")
        self._max.setToolTip("Maximise")
        self._max.clicked.connect(self.maximise_requested.emit)

        self._close = QPushButton("✕")
        self._close.setObjectName("winclose")
        self._close.setToolTip("Close to the corner")
        self._close.clicked.connect(self.dismiss_requested.emit)

        for b in (self._min, self._max, self._close):
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedSize(30, 26)
            row.addWidget(b, 0, Qt.AlignVCenter)
        return bar

    # ── page switching ────────────────────────────────────
    def _select(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None and key in self._page_factories:
            page = self._page_factories[key]()
            if key == "settings" and hasattr(page, "restyle_needed"):
                page.restyle_needed.connect(self._restyle_all)
            self._pages[key] = page
            self.stack.addWidget(page)
        if page is not None:
            # history/memory reflect live state, so refresh on entry
            if hasattr(page, "reload"):
                try:
                    page.reload()
                except Exception:
                    pass
            self.stack.setCurrentWidget(page)
        self.sidebar.set_active(key)
        if key == "chat":
            self.input.focus()

    def showing_overlay(self) -> bool:
        return self.stack.currentWidget() is not self.chat

    def close_overlays(self) -> None:
        self._select("chat")

    # ── state fan-out ─────────────────────────────────────
    def _on_state(self, state: str) -> None:
        self.sidebar.set_state(state)
        self.state_changed.emit(state)

    # ── controller contract: conversation (delegated) ─────
    def add_user_message(self, text, attachments=None):
        self.chat.add_user_message(text, attachments)

    def begin_mike_stream(self):
        return self.chat.begin_mike_stream()

    def add_mike_message(self, text):
        self.chat.add_mike_message(text)

    def add_action_card(self, text):
        return self.chat.add_action_card(text)

    def show_thinking(self):
        self.chat.show_thinking()

    def hide_thinking(self):
        self.chat.hide_thinking()

    def set_state(self, state):
        self.chat.set_state(state)

    def state(self):
        return self.chat.state()

    def take_attachments(self):
        return self.chat.take_attachments()

    def add_attachments(self, paths):
        self.chat.add_attachments(paths)

    def clear(self):
        self._select("chat")
        self.chat.clear()

    def set_maximised(self, on: bool) -> None:
        self._maximised = on
        self._max.setText("❐" if on else "▢")
        self._max.setToolTip("Restore" if on else "Maximise")
        self.update()

    def desired_height(self) -> int:
        # The workspace is a real window sized by the user / saved geometry,
        # not by its content. Kept for contract compatibility.
        return max(self.height(), 640)

    # ── live re-theme (accent / light-dark switch) ────────
    def _restyle_all(self) -> None:
        style.apply_theme()
        self.setStyleSheet(self._qss())
        # rebuild the chat page's own stylesheet and repaint painted widgets
        try:
            from ui.panel.mike_panel import _build_stylesheet
            self.chat.setStyleSheet(_build_stylesheet())
        except Exception:
            pass
        self.sidebar.setStyleSheet(
            f"QWidget#sidebar {{ background:{style.GROUND_SUNK}; "
            f"border-right:1px solid {style.HAIRLINE}; }}")
        # drop cached secondary pages so they rebuild with the new palette
        for key in list(self._pages):
            if key == "chat":
                continue
            w = self._pages.pop(key)
            if self.stack.currentWidget() is w:
                self.stack.setCurrentWidget(self.chat)
                self.sidebar.set_active("chat")
            self.stack.removeWidget(w)
            w.deleteLater()
        for w in self.findChildren(QWidget):
            w.update()
        self.update()

    def _qss(self) -> str:
        return f"""
QWidget#titlebar {{ background: transparent; }}
QPushButton#winbtn {{
    background: transparent; color: {style.INK_MUTE};
    border: none; border-radius: 7px; font-size: 13px;
}}
QPushButton#winbtn:hover {{ background: {style.GROUND_RAISED}; color: {style.INK}; }}
QPushButton#winclose {{
    background: transparent; color: {style.INK_MUTE};
    border: none; border-radius: 7px; font-size: 13px;
}}
QPushButton#winclose:hover {{ background: {style.STOP}; color: #FFFFFF; }}
"""

    # ── the window material: an opaque rounded surface ────
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        radius = 0.0 if self._maximised else 12.0
        rect = QRectF(0, 0, self.width(), self.height())
        body = QPainterPath()
        body.addRoundedRect(rect, radius, radius)
        p.fillPath(body, QColor(style.GROUND))
        if not self._maximised:
            pen = QPen(QColor(style.HAIRLINE))
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
