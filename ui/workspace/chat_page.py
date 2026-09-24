"""The conversation workspace — the main surface of FULL MIKE.

Laid out like a chat people already know: Mike's answers start at the left
edge (rendered Markdown, code with copy, tables), your messages sit in quiet
bubbles on the right, an inline ledger appears while he works, a first-class
confirmation when he needs you, and the composer runs along the bottom with
attachments and voice. It fills the space it's given and scrolls as the
conversation grows.

It reuses the proven message/ledger/confirm/input widgets from the panel and
implements exactly the slice of the controller contract that concerns the
conversation, so nothing under it changes.
"""
from __future__ import annotations

import os
from html import escape

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mike_panel import (
    _ActivityFacade, _AttachChip, _ConversationFacade, _Confirm, _InputBar,
    _Ledger, _RichTurn, _Starters, _Turn, _ActionHandle, _animate_entry,
    _build_stylesheet,
)
from ui.workspace.thinking import ThinkingLine

#: Mike's text starts at the left and runs no wider than this — beyond it a
#: line of prose gets tiring to read on a maximised window.
MIKE_MAX = 900
#: Your messages wrap inside a bubble no wider than this.
USER_MAX = 560
#: Breathing room between the conversation and the window edges.
SIDE_PAD = 36


class _UserBubble(QWidget):
    """Your message, in a quiet bubble on the right — like any chat."""

    def __init__(self, text: str, attachments: list[str] | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._raw = text
        self.setStyleSheet("background:transparent;")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        parts = []
        if attachments:
            # One line per file, kept whole (no wrap between the clip and the
            # name), then a real line break before what you typed.
            files = "<br>".join(
                f'<span style="color:{style.INK_MUTE}; font-size:12px; '
                f'white-space:nowrap;">&#128206;&nbsp;{escape(os.path.basename(a))}</span>'
                for a in attachments)
            parts.append(files)
        if text:
            parts.append(escape(text).replace("\n", "<br>"))

        label = QLabel("<br>".join(parts))
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setMaximumWidth(USER_MAX)
        # Same reading size as Mike's replies (16px), so neither side shouts.
        label.setFont(style.voice(12))
        label.setStyleSheet(
            f"QLabel{{background:{style.GROUND_RAISED}; color:{style.INK};"
            f"border:1px solid {style.HAIRLINE}; border-radius:16px;"
            f"padding:10px 15px;}}")
        row.addWidget(label, 0, Qt.AlignRight)


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

        # ── the conversation, scrolling, starting from the left ──
        self._scroll = QScrollArea()
        self._scroll.setObjectName("stage")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)

        column = QWidget()
        column.setStyleSheet("background:transparent;")
        self._stage = QVBoxLayout(column)
        self._stage.setContentsMargins(SIDE_PAD, 28, SIDE_PAD, 16)
        self._stage.setSpacing(18)
        self._stage.addStretch(1)

        self._scroll.setWidget(column)
        outer.addWidget(self._scroll, 1)

        self.conversation = _ConversationFacade(self._scroll)
        self.activity = _ActivityFacade()

        # ── the composer: confirm + chips + input, along the bottom ──
        composer = QWidget()
        composer.setObjectName("composer")
        composer.setStyleSheet("background:transparent;")
        col = QVBoxLayout(composer)
        col.setContentsMargins(SIDE_PAD - 8, 10, SIDE_PAD - 8, 18)
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
        self._resting.setMaximumWidth(MIKE_MAX)
        self._insert(self._resting)
        if first_run:
            self._starters = _Starters()
            self._starters.setMaximumWidth(MIKE_MAX)
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
    def _insert(self, widget: QWidget, animate: bool = True) -> None:
        self._stage.insertWidget(self._stage.count() - 1, widget)
        if animate:
            _animate_entry(widget)
        self.conversation.scroll_to_bottom()

    def _mike_turn(self, text: str) -> _RichTurn:
        turn = _RichTurn(text)
        turn.setMaximumWidth(MIKE_MAX)
        return turn

    # ── controller contract: conversation ─────────────────
    def add_user_message(self, text: str, attachments: list[str] | None = None) -> None:
        self._drop_resting()
        self._insert(_UserBubble(text, attachments))
        self._ledger = None

    def begin_mike_stream(self) -> _RichTurn:
        self._drop_resting()
        self._stream = self._mike_turn("")
        self._insert(self._stream)
        return self._stream

    def add_mike_message(self, text: str) -> None:
        self._drop_resting()
        self._insert(self._mike_turn(text))

    def add_action_card(self, text: str) -> _ActionHandle:
        self._drop_resting()
        if self._ledger is None:
            self._ledger = _Ledger()
            self._ledger.setMaximumWidth(MIKE_MAX)
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

    def _clear_stage(self) -> None:
        self.hide_thinking()
        while self._stage.count() > 1:
            item = self._stage.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._resting = None
        self._starters = None
        self._stream = None
        self._ledger = None

    def clear(self) -> None:
        self._clear_stage()
        self._show_resting()
        self.set_state("idle")

    def show_conversation(self, turns: list[dict]) -> None:
        """Lay a saved conversation back out, exactly as it was said."""
        self._clear_stage()
        for t in turns:
            if t.get("role") == "user":
                self._insert(_UserBubble(t.get("content", ""), t.get("attachments")),
                             animate=False)
            elif t.get("role") == "assistant":
                self._insert(self._mike_turn(t.get("content", "")), animate=False)
        if not turns:
            self._show_resting()
        QTimer.singleShot(50, self.conversation.scroll_to_bottom)

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
