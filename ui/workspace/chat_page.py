"""The conversation workspace — the main surface of FULL MIKE.

A centred reading column that fills the window: Mike's answers rendered
(Markdown, code with copy, tables), your prompts quietly above them, an inline
ledger while he works, a first-class confirmation when he needs you, and the
input anchored at the bottom with attachments and voice. Unlike the old panel
this does not size itself to its content — it is a real workspace that fills
the space it's given and scrolls when the conversation grows.

It reuses the proven message/ledger/confirm/input widgets from the panel
(they were always about presentation, not the panel's floating shape) and
implements exactly the slice of the controller contract that concerns the
conversation, so nothing under it changes.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mike_panel import (
    _ActivityFacade, _AttachChip, _ConversationFacade, _Confirm, _InputBar,
    _Ledger, _RichTurn, _Starters, _Turn, _ActionHandle, _animate_entry,
    _build_stylesheet, STATE_WORD,
)
from ui.workspace.thinking import ThinkingLine

#: The reading column never grows past this; text set wider than this is
#: tiring to read and makes the workspace feel empty. Everything centres in it.
COLUMN_MAX = 760


def _centered(inner: QWidget, max_width: int = COLUMN_MAX) -> QWidget:
    """Wrap a widget so it centres in its parent and caps its width."""
    holder = QWidget()
    holder.setStyleSheet("background:transparent;")
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    row.addStretch(1)
    inner.setMaximumWidth(max_width)
    row.addWidget(inner, 1)
    row.addStretch(1)
    return holder


class ChatPage(QWidget):

    state_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state = "idle"
        self._stream: _RichTurn | None = None
        self._ledger: _Ledger | None = None
        self._thinking: ThinkingLine | None = None
        self._attachments: list[str] = []
        self._build()
        self.set_state("idle")

    # ── construction ──────────────────────────────────────
    def _build(self) -> None:
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_build_stylesheet())
        self.setObjectName("chatPage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── the conversation, scrolling, centred ──
        self._scroll = QScrollArea()
        self._scroll.setObjectName("stage")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)

        board = QWidget()
        board.setStyleSheet("background:transparent;")
        board_row = QHBoxLayout(board)
        board_row.setContentsMargins(0, 0, 0, 0)
        board_row.addStretch(1)

        column = QWidget()
        column.setStyleSheet("background:transparent;")
        column.setMaximumWidth(COLUMN_MAX)
        self._stage = QVBoxLayout(column)
        self._stage.setContentsMargins(8, 28, 8, 16)
        self._stage.setSpacing(20)
        self._stage.addStretch(1)
        board_row.addWidget(column, 1)
        board_row.addStretch(1)

        self._scroll.setWidget(board)
        outer.addWidget(self._scroll, 1)

        self.conversation = _ConversationFacade(self._scroll)
        self.activity = _ActivityFacade()

        # ── the composer: confirm + chips + input, centred to the column ──
        composer = QWidget()
        composer.setObjectName("composer")
        cwrap = QHBoxLayout(composer)
        cwrap.setContentsMargins(0, 0, 0, 0)
        cwrap.addStretch(1)

        stack = QWidget()
        stack.setStyleSheet("background:transparent;")
        stack.setMaximumWidth(COLUMN_MAX)
        col = QVBoxLayout(stack)
        col.setContentsMargins(8, 10, 8, 18)
        col.setSpacing(8)

        self.confirm = _Confirm()
        self.confirm.visibility_changed.connect(
            lambda: QTimer.singleShot(0, self.conversation.scroll_to_bottom))
        col.addWidget(self.confirm)

        self._chips = QWidget()
        self._chips.setStyleSheet("background:transparent;")
        self._chips_row = QHBoxLayout(self._chips)
        self._chips_row.setContentsMargins(4, 0, 4, 0)
        self._chips_row.setSpacing(6)
        self._chips_row.addStretch(1)
        self._chips.hide()
        col.addWidget(self._chips)

        self.input = _InputBar()
        self.input.attach_requested.connect(self.add_attachments)
        col.addWidget(self.input)

        cwrap.addWidget(stack, 1)
        cwrap.addStretch(1)
        outer.addWidget(composer)

        self.setAcceptDrops(True)
        self._show_resting()

    # ── resting / greeting ────────────────────────────────
    def _show_resting(self) -> None:
        from config import preferences

        first_run = not bool(preferences.get("onboarding_complete", False))
        name = str(preferences.get("profile_name", "") or "").strip()
        if first_run:
            text = (
                f"I'm Mike. I live on this PC — and unlike a chat window, I can "
                "actually use it.\n\nOpen things, find files, write something, "
                "fix code that won't run. I check before changing anything, and "
                "nothing leaves this machine."
            )
        else:
            from datetime import datetime
            h = datetime.now().hour
            part = ("Good morning" if 5 <= h < 12 else "Good afternoon"
                    if 12 <= h < 17 else "Good evening" if 17 <= h < 22 else "Still here")
            who = f", {name}" if name else ""
            text = f"{part}{who}. What are we working on?"

        self._resting = _Turn(text, "mike")
        self._insert(self._resting)
        if first_run:
            self._starters = _Starters()
            self._starters.picked.connect(self._on_starter)
            self._insert(self._starters)
            preferences.set_value("onboarding_complete", True)

    def _on_starter(self, prompt: str) -> None:
        self._drop_resting()
        self.conversation.suggestion_clicked.emit(prompt)

    def _drop_resting(self) -> None:
        for name in ("_resting", "_starters"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.hide()
                self._stage.removeWidget(widget)
                widget.deleteLater()
                setattr(self, name, None)

    # ── column helpers ────────────────────────────────────
    def _insert(self, widget: QWidget) -> None:
        self._stage.insertWidget(self._stage.count() - 1, widget)
        _animate_entry(widget)
        self.conversation.scroll_to_bottom()

    # ── controller contract: conversation ─────────────────
    def add_user_message(self, text: str, attachments: list[str] | None = None) -> None:
        self._drop_resting()
        shown = text
        if attachments:
            names = ", ".join(os.path.basename(a) for a in attachments)
            tag = f"\U0001F4CE {names}"
            shown = f"{tag}\n{text}" if text else tag
        self._insert(_Turn(shown, "you"))
        self._ledger = None

    def begin_mike_stream(self) -> _RichTurn:
        self._drop_resting()
        self._stream = _RichTurn("")
        self._insert(self._stream)
        return self._stream

    def add_mike_message(self, text: str) -> None:
        self._drop_resting()
        self._insert(_RichTurn(text))

    def add_action_card(self, text: str) -> _ActionHandle:
        self._drop_resting()
        if self._ledger is None:
            self._ledger = _Ledger()
            self._insert(self._ledger)
        index = self._ledger.add_row(text)
        self.set_state("working")
        return _ActionHandle(self._ledger, index, text)

    def show_thinking(self) -> None:
        self.hide_thinking()
        self._drop_resting()
        self._thinking = ThinkingLine(size=15)
        self._insert(self._thinking)
        self._thinking.start()

    def hide_thinking(self) -> None:
        if self._thinking is not None:
            self._thinking.stop()
            self._thinking.hide()
            self._stage.removeWidget(self._thinking)
            self._thinking.deleteLater()
            self._thinking = None

    def set_state(self, state: str) -> None:
        self._state = state
        self.input.voice.set_state(state)
        self.input.set_listening(state == "listening")
        self.input.set_responding(
            state in ("thinking", "working", "responding", "speaking"))
        self.state_changed.emit(state)

    def state(self) -> str:
        return self._state

    def clear(self) -> None:
        while self._stage.count() > 1:
            item = self._stage.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._resting = None
        self._starters = None
        self._stream = None
        self._ledger = None
        self._thinking = None
        self._show_resting()
        self.set_state("idle")

    # ── attachments ───────────────────────────────────────
    def add_attachments(self, paths: list[str]) -> None:
        for path in paths:
            if path and os.path.exists(path) and path not in self._attachments:
                self._attachments.append(path)
        self._refresh_chips()

    def take_attachments(self) -> list[str]:
        pending = list(self._attachments)
        self._attachments.clear()
        self._refresh_chips()
        return pending

    def _refresh_chips(self) -> None:
        while self._chips_row.count() > 1:
            item = self._chips_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for path in self._attachments:
            chip = _AttachChip(os.path.basename(path), path)
            chip.removed.connect(self._remove_attachment)
            self._chips_row.insertWidget(self._chips_row.count() - 1, chip)
        self._chips.setVisible(bool(self._attachments))

    def _remove_attachment(self, path: str) -> None:
        if path in self._attachments:
            self._attachments.remove(path)
        self._refresh_chips()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_attachments(paths)
            event.acceptProposedAction()
