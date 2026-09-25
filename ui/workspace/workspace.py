"""FULL MIKE — the desktop workspace.

A real application window: the rail of conversations down the left (it folds
away with Ctrl+B or its toggle), and on the right a slim titlebar naming the
chat you're in, with the conversation — or Settings — beneath it. It
re-exposes exactly the contract UIController speaks (input / conversation /
confirm / activity and the add_* / begin_* / set_state / *_requested surface)
by delegating the conversation calls to the chat page, so the engine
underneath is untouched — the window is a shell around the same Mike.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.workspace.chat_page import ChatPage
from ui.workspace.icons import IconButton
from ui.workspace.sidebar import Sidebar, sidebar_qss


class MikeWorkspace(QWidget):

    # the controller listens for state; the window for the chrome actions
    state_changed = Signal(str)
    dismiss_requested = Signal()
    minimise_requested = Signal()
    maximise_requested = Signal()

    TITLE_H = Sidebar.TOP_H

    def __init__(self, settings_hooks: dict | None = None) -> None:
        super().__init__()
        self._hooks = settings_hooks if settings_hooks is not None else {}
        self._maximised = False
        self._settings = None
        self._conversation_id: int | None = None
        self._fold_anim: QPropertyAnimation | None = None
        self._sidebar_open = True
        self._build()

    # ── construction ──────────────────────────────────────
    def _build(self) -> None:
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.new_chat_requested.connect(self._new_chat)
        self.sidebar.conversation_opened.connect(self._open_conversation)
        self.sidebar.conversation_deleted.connect(self._delete_conversation)
        self.sidebar.settings_requested.connect(self._open_profile)
        self.sidebar.collapse_requested.connect(self.toggle_sidebar)
        root.addWidget(self.sidebar)

        main = QWidget()
        mcol = QVBoxLayout(main)
        mcol.setContentsMargins(0, 0, 0, 0)
        mcol.setSpacing(0)
        mcol.addWidget(self._titlebar())

        self.stack = QStackedWidget()
        mcol.addWidget(self.stack, 1)
        root.addWidget(main, 1)

        # ── the pages ──
        self.chat = ChatPage()
        self.chat.state_changed.connect(self._on_state)
        self.stack.addWidget(self.chat)

        # ── the controller contract: delegate conversation to the chat page ──
        self.input = self.chat.input
        self.conversation = self.chat.conversation
        self.confirm = self.chat.confirm
        self.activity = self.chat.activity

        # the profile row and Settings need to hear about each other
        self._hooks.setdefault("profile_changed", self._on_profile_changed)

        # Is the brain ready? Checked at startup and on demand; the chat shows
        # a banner with the fix, Settings shows the live status.
        from ui.workspace.health import BrainHealth
        self.health = BrainHealth(self)
        self.health.changed.connect(self.chat.brain_banner.show_health)
        self.chat.brain_banner.start_requested.connect(self.health.start_ollama)
        self.chat.brain_banner.retry_requested.connect(self.health.check)
        self._hooks["brain_health"] = self.health
        self._hooks.setdefault("chats_deleted", self._on_chats_deleted)

        # The account: the profile row, the greeting and Settings follow it,
        # and being signed out by the server is said out loud.
        from account.manager import manager
        account = manager()
        account.changed.connect(self._on_account_changed)
        account.notice.connect(lambda text: self.chat.add_notice(text, "info"))

        from config import preferences
        if bool(preferences.get("sidebar_collapsed", False)):
            self._sidebar_open = False
            self.sidebar.setMaximumWidth(0)
            self.sidebar.hide()
        self._sync_fold_buttons()
        self.refresh_conversations()
        self._sync_title()
        self.setStyleSheet(self._qss())

    def _titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titlebar")
        bar.setFixedHeight(self.TITLE_H)
        bar.setAttribute(Qt.WA_StyledBackground, True)
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 0, 10, 0)
        row.setSpacing(4)

        # shown only while the rail is folded away, so the way back is where
        # the rail's own toggle was
        self._unfold = IconButton("sidebar", "Show sidebar (Ctrl+B)", size=32, icon_size=18)
        self._unfold.clicked.connect(self.toggle_sidebar)
        row.addWidget(self._unfold, 0, Qt.AlignVCenter)
        self._compose = IconButton("compose", "New chat (Ctrl+N)", size=32, icon_size=18)
        self._compose.clicked.connect(self._new_chat)
        row.addWidget(self._compose, 0, Qt.AlignVCenter)
        row.addSpacing(6)

        self._title = QLabel("")
        self._title.setObjectName("chatTitle")
        self._title.setFont(style.font(style.BODY, QFont.Weight.Medium))
        self._title.setStyleSheet(f"color:{style.INK_SOFT};background:transparent;")
        self._title.setMinimumWidth(40)
        row.addWidget(self._title, 1, Qt.AlignVCenter)

        self._min = IconButton("minimise", "Minimise to the corner", size=34, icon_size=16)
        self._min.clicked.connect(self.minimise_requested.emit)
        self._max = IconButton("maximise", "Maximise", size=34, icon_size=16)
        self._max.clicked.connect(self.maximise_requested.emit)
        self._close = IconButton("close", "Close to the corner — Mike keeps running",
                                 size=34, icon_size=16, variant="danger-hover")
        self._close.clicked.connect(self.dismiss_requested.emit)
        for b in (self._min, self._max, self._close):
            row.addWidget(b, 0, Qt.AlignVCenter)
        return bar

    # ── the rail: fold / unfold ───────────────────────────
    def sidebar_open(self) -> bool:
        return self._sidebar_open

    def toggle_sidebar(self) -> None:
        self.set_sidebar_open(not self.sidebar_open())

    def set_sidebar_open(self, on: bool) -> None:
        from config import preferences
        preferences.set_value("sidebar_collapsed", not on)
        self._sidebar_open = on
        if self._fold_anim is not None:
            self._fold_anim.stop()
        target = Sidebar.WIDTH if on else 0
        if on:
            self.sidebar.show()
        if style.reduced_motion() or not self.isVisible():
            self.sidebar.setMaximumWidth(target)
            self.sidebar.setVisible(on)
            self._sync_fold_buttons()
            return
        anim = QPropertyAnimation(self.sidebar, b"maximumWidth", self)
        anim.setDuration(200)
        anim.setStartValue(self.sidebar.width() if self.sidebar.isVisible() else 0)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: (self.sidebar.setVisible(on), self._sync_fold_buttons()))
        self._fold_anim = anim
        # the titlebar's own toggle appears as soon as the rail starts to go
        self._unfold.setVisible(not on)
        self._compose.setVisible(not on)
        anim.start()

    def _sync_fold_buttons(self) -> None:
        folded = not self.sidebar_open()
        self._unfold.setVisible(folded)
        self._compose.setVisible(folded)

    # ── page switching ────────────────────────────────────
    def open_settings(self, tab: str | None = None) -> None:
        if self._settings is None:
            from ui.workspace.pages import SettingsPage
            self._settings = SettingsPage(self._hooks)
            self._settings.restyle_needed.connect(self._restyle_all)
            self._settings.closed.connect(self.close_overlays)
            self.stack.addWidget(self._settings)
        else:
            self._settings.reload()
        if tab:
            self._settings.open_tab(tab)
        self.stack.setCurrentWidget(self._settings)
        self.sidebar.set_current(None)
        # the page carries its own large title; the titlebar stays quiet
        self._title.setText("")

    def showing_overlay(self) -> bool:
        return self.stack.currentWidget() is not self.chat

    def close_overlays(self) -> None:
        self.stack.setCurrentWidget(self.chat)
        self.sidebar.set_current(self._conversation_id)
        self._sync_title()
        self.input.focus()

    # kept for callers that navigate by key
    def _select(self, key: str) -> None:
        if key == "chat":
            self.close_overlays()
        else:
            self.open_settings(key if key != "settings" else None)

    # ── conversations ─────────────────────────────────────
    def refresh_conversations(self) -> None:
        try:
            from brain import conversation_store
            convos = conversation_store.recent(limit=200)
        except Exception:
            convos = []
        self.sidebar.set_conversations(convos, self._conversation_id)

    def conversation_changed(self, conversation_id: int | None) -> None:
        """The controller's chat changed (new, reopened, or its first message):
        mark it in the rail and name it in the titlebar."""
        self._conversation_id = conversation_id
        self.refresh_conversations()
        if not self.showing_overlay():
            self._sync_title()

    def _sync_title(self) -> None:
        title = ""
        if self._conversation_id is not None:
            try:
                from brain import conversation_store
                convo = conversation_store.get(self._conversation_id)
                title = (convo or {}).get("title") or ""
            except Exception:
                title = ""
        self._title.setText(title or "New chat")

    def _open_conversation(self, conversation_id: int) -> None:
        hook = self._hooks.get("open_conversation")
        if hook:
            hook(conversation_id)
        self.close_overlays()

    def _delete_conversation(self, conversation_id: int) -> None:
        try:
            from brain import conversation_store
            conversation_store.delete(conversation_id)
        except Exception:
            pass
        # Deleting the chat you're in starts a fresh one, rather than leaving
        # a conversation on screen that no longer exists to be continued.
        getter = self._hooks.get("current_conversation")
        try:
            is_current = getter is not None and getter() == conversation_id
        except Exception:
            is_current = False
        if is_current and self._hooks.get("new_conversation"):
            self._hooks["new_conversation"]()
        else:
            self.refresh_conversations()

    def _new_chat(self) -> None:
        # The controller owns what a new chat means (Mike forgetting the old
        # one too, not just a cleared screen), so the rail only asks.
        hook = self._hooks.get("new_conversation")
        if hook:
            hook()
        else:
            self.clear()
        self.close_overlays()

    def set_wake_listening(self, on: bool) -> None:
        """Whether "Hey Mike" is really live, so hints only promise what works."""
        self.chat._hero.set_wake_listening(on)

    def _on_chats_deleted(self) -> None:
        """Every chat was erased from Settings: start fresh, empty the rail."""
        hook = self._hooks.get("new_conversation")
        if hook:
            hook()
        self.refresh_conversations()
        if self._settings is not None and self.showing_overlay():
            self.stack.setCurrentWidget(self._settings)

    def _on_profile_changed(self) -> None:
        self.sidebar.refresh_profile()

    def _on_account_changed(self) -> None:
        self.sidebar.refresh_profile()
        self.chat.refresh_greeting()

    def _open_profile(self) -> None:
        """The profile row opens Settings at your account, when there is one."""
        from account import config as account_config
        self.open_settings("account" if account_config.configured() else None)

    # ── state fan-out ─────────────────────────────────────
    def _on_state(self, state: str) -> None:
        self.sidebar.set_state(state)
        self.state_changed.emit(state)

    # ── controller contract: conversation (delegated) ─────
    def add_user_message(self, text, attachments=None):
        if self.showing_overlay():
            self.close_overlays()
        self.chat.add_user_message(text, attachments)

    def begin_mike_stream(self):
        return self.chat.begin_mike_stream()

    def add_mike_message(self, text):
        self.chat.add_mike_message(text)

    def add_notice(self, text, kind="error"):
        self.chat.add_notice(text, kind)
        if kind == "error":
            # an error is often the brain going away — re-check, so the banner
            # can offer the fix
            self.health.check()

    def add_action_card(self, text):
        return self.chat.add_action_card(text)

    def mark_stopped(self):
        self.chat.mark_stopped()

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
        self.close_overlays()
        self.chat.clear()

    def show_conversation(self, turns):
        """Show a saved chat (reopened from the rail, or resumed at launch)."""
        self.close_overlays()
        self.chat.show_conversation(turns)

    def set_maximised(self, on: bool) -> None:
        self._maximised = on
        self.sidebar.set_rounded(not on)
        self._max.set_icon("restore" if on else "maximise")
        self._max.setToolTip("Restore" if on else "Maximise")
        self.update()

    def desired_height(self) -> int:
        # The workspace is a real window sized by the user / saved geometry,
        # not by its content. Kept for contract compatibility.
        return max(self.height(), 640)

    def hit_is_caption(self, pos: QPoint) -> bool:
        """Is this point (window coordinates) empty titlebar — a place to drag
        the window from — rather than a control or content?"""
        if pos.y() < 0 or pos.y() >= self.TITLE_H:
            return False
        w = self.childAt(pos)
        while w is not None and w is not self:
            if isinstance(w, QAbstractButton):
                return False
            w = w.parentWidget()
        return True

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
        self.sidebar.setStyleSheet(sidebar_qss())
        try:
            self.input._restyle()
        except Exception:
            pass
        # Settings is rebuilt in the new palette — and reopened on the tab you
        # were on, rather than dropping you back into the chat mid-change.
        was_open = self.showing_overlay()
        tab = self._settings.current_tab() if self._settings is not None else None
        if self._settings is not None:
            old = self._settings
            self._settings = None
            self.stack.setCurrentWidget(self.chat)
            self.stack.removeWidget(old)
            old.hide()
            old.deleteLater()
        if was_open:
            self.open_settings(tab)
        for w in self.findChildren(QWidget):
            w.update()
        self.update()

    def _qss(self) -> str:
        return """
QWidget#titlebar { background: transparent; }
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
