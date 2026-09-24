"""The conversation — the main surface of FULL MIKE.

Laid out like a chat people already know, in one centred reading column: your
messages in quiet bubbles on the right, Mike's answers from the left (rendered
Markdown, maths, code with copy), a live card of steps while he works on your
computer, a first-class confirmation when he needs you, and the composer along
the bottom with files, voice, and Send / Stop.

An empty chat isn't a blank page: it greets you and offers the things people
actually come to Mike for — understand a PDF, work a problem through, fix code,
do something on the PC — each of which either starts the message for you or
runs something verified to work.

It implements exactly the slice of the controller contract that concerns the
conversation, so nothing under it changes.
"""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mark import PresenceMark
from ui.panel.mike_panel import (
    _ActivityFacade, _ConversationFacade, _Confirm, _RichTurn, _ActionHandle,
    _animate_entry, _build_stylesheet, _hotkey_hint, _this_machine,
)
from ui.workspace.composer import Composer, _ChipIcon
from ui.workspace.icons import draw
from ui.workspace.steps import StepsCard
from ui.workspace.thinking import ThinkingLine

#: The reading column: wide enough for code and tables, narrow enough that a
#: line of prose stays comfortable on a maximised window.
COLUMN = 780
#: Your messages wrap inside a bubble no wider than this.
USER_MAX = 560
#: Breathing room between the column and the window edges.
SIDE_PAD = 28


class _FollowingScroll(_ConversationFacade):
    """Keeps the newest message in view — unless you've scrolled up to read.

    Streaming used to pull the view to the bottom on every token, so reading
    back over an earlier answer while Mike wrote the next one was impossible.
    It follows only when you're already at (or near) the bottom; your own new
    message always brings it down.
    """

    NEAR = 96   # px from the bottom that still counts as "at the bottom"

    def __init__(self, scroll: QScrollArea) -> None:
        super().__init__(scroll)
        self._stick = True
        bar = scroll.verticalScrollBar()
        # Follow growth rather than chase it: when the content gets taller and
        # we're pinned to the bottom, move to the new bottom. (Scrolling on a
        # zero-timer after an insert could land before the layout grew, and
        # then every later token thought you had scrolled away.)
        bar.valueChanged.connect(self._on_value)
        bar.rangeChanged.connect(self._on_range)

    def _on_value(self, value: int) -> None:
        self._stick = value >= self._scroll.verticalScrollBar().maximum() - self.NEAR

    def _on_range(self, _lo: int, hi: int) -> None:
        if self._stick:
            self._scroll.verticalScrollBar().setValue(hi)

    def scroll_to_bottom(self, force: bool = False) -> None:
        if force:
            self._stick = True
        if self._stick:
            bar = self._scroll.verticalScrollBar()
            QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))


def _centred(widget: QWidget, max_width: int = COLUMN) -> QWidget:
    outer = QWidget()
    row = QHBoxLayout(outer)
    row.setContentsMargins(SIDE_PAD, 0, SIDE_PAD, 0)
    row.setSpacing(0)
    row.addStretch(1)
    widget.setMaximumWidth(max_width)
    row.addWidget(widget, 100)
    row.addStretch(1)
    return outer


class _UserBubble(QWidget):
    """Your message, in a quiet bubble on the right — like any chat."""

    def __init__(self, text: str, attachments: list[str] | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._raw = text
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        bubble = QFrame()
        bubble.setObjectName("userBubble")
        bubble.setMaximumWidth(USER_MAX)
        bubble.setStyleSheet(
            f"QFrame#userBubble{{background:{style.GROUND_RAISED};"
            f"border:1px solid {style.HAIRLINE};border-radius:18px;}}")
        col = QVBoxLayout(bubble)
        col.setContentsMargins(16, 10, 16, 11)
        col.setSpacing(6)
        for a in attachments or []:
            line = QHBoxLayout()
            line.setSpacing(8)
            line.addWidget(_ChipIcon(os.path.splitext(a)[1].lower()), 0, Qt.AlignVCenter)
            name = QLabel(os.path.basename(a))
            name.setFont(style.font(style.SMALL, QFont.Weight.Medium))
            name.setStyleSheet(f"color:{style.INK_SOFT};background:transparent;")
            name.setToolTip(a)
            line.addWidget(name, 1, Qt.AlignVCenter)
            col.addLayout(line)
        if text:
            label = QLabel(text)
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            # The same reading size as Mike's replies, so neither side shouts.
            label.setFont(style.font(style.READ))
            label.setStyleSheet(f"color:{style.INK};background:transparent;")
            col.addWidget(label)
        row.addWidget(bubble, 0, Qt.AlignRight)


class _Notice(QFrame):
    """Something about the conversation rather than in it: an error Mike hit,
    or the fact that you stopped him."""

    def __init__(self, text: str, kind: str = "error", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("notice")
        self._kind = kind
        row = QHBoxLayout(self)
        row.setSpacing(10)
        quiet = kind in ("stopped", "info")
        if quiet:
            row.setContentsMargins(2, 0, 2, 0)
        else:
            row.setContentsMargins(14, 12, 16, 12)
        icon = _NoticeIcon(kind)
        row.addWidget(icon, 0, Qt.AlignTop)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if quiet:
            label.setFont(style.font(style.SMALL))
            label.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
        else:
            label.setFont(style.font(style.BODY))
            label.setStyleSheet(f"color:{style.INK};background:transparent;")
        row.addWidget(label, 1)
        if kind == "error":
            tint = QColor(style.STOP)
            tint.setAlpha(22)
            self.setStyleSheet(
                f"QFrame#notice{{background:rgba({tint.red()},{tint.green()},{tint.blue()},"
                f"{tint.alpha()});border:1px solid {style.STOP};border-radius:12px;}}")
        else:
            self.setStyleSheet("QFrame#notice{background:transparent;border:none;}")


class _NoticeIcon(QWidget):
    def __init__(self, kind: str, parent=None) -> None:
        super().__init__(parent)
        self._kind = kind
        self.setFixedSize(18, 18)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self._kind == "error":
            draw(p, "warning", QRectF(0, 0, 18, 18), QColor(style.STOP), 1.6)
        elif self._kind == "info":
            draw(p, "info", QRectF(1, 1, 16, 16), QColor(style.INK_MUTE), 1.5)
        else:
            col = QColor(style.INK_MUTE)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(5, 5, 8, 8), 2, 2)


class ConfirmCard(_Confirm):
    """The confirmation, in the workspace's type scale, with a long preview
    (an edit's before/after) kept scrollable so the buttons never leave the
    screen."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QScrollArea as _SA
        self._head.setFont(style.font(style.SMALL, QFont.Weight.DemiBold))
        self._head.setStyleSheet(f"color:{style.WARN};background:transparent;")
        self._body.setFont(style.font(style.READ))
        self._body.setTextFormat(Qt.PlainText)
        self._body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._consequence.setFont(style.font(style.SMALL, QFont.Weight.Medium))
        for b in (self._deny, self._allow):
            b.setFont(style.font(style.BODY, QFont.Weight.DemiBold))
            b.setMinimumHeight(36)
        self._allow.setToolTip("Let Mike do this")
        self._deny.setToolTip("Don't do this (Esc)")
        lay = self.layout()
        index = lay.indexOf(self._body)
        lay.removeWidget(self._body)
        wrap = _SA()
        wrap.setObjectName("confirmBody")
        wrap.setWidgetResizable(True)
        wrap.setFrameShape(QFrame.NoFrame)
        wrap.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        wrap.setStyleSheet("QScrollArea#confirmBody{background:transparent;border:none;}")
        wrap.setWidget(self._body)
        self._body_wrap = wrap
        lay.insertWidget(index, wrap)

    def ask(self, description: str) -> None:
        super().ask(description)
        danger = bool(self.property("danger"))
        self._head.setText("Mike wants to make a permanent change" if danger
                           else "Mike needs your OK to continue")
        self._head.setStyleSheet(
            f"color:{style.STOP if danger else style.WARN};background:transparent;")
        self._dot.setStyleSheet(
            f"color:{style.STOP if danger else style.WARN};background:transparent;font-size:9px;")
        # size the preview to its text, up to a cap, then scroll
        width = max(300, self._body_wrap.viewport().width() or 600)
        need = self._body.heightForWidth(width) + 4
        self._body_wrap.setFixedHeight(max(24, min(need, 220)))


class _Suggestion(QWidget):
    """One thing to try on an empty chat."""

    clicked = Signal()

    def __init__(self, icon: str, title: str, desc: str, parent=None) -> None:
        super().__init__(parent)
        self._icon, self._title, self._desc = icon, title, desc
        self._hover = False
        self.setFixedHeight(74)
        self.setMinimumWidth(220)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(title)
        self.setToolTip(desc)

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
        p.setPen(QColor(style.INK_MUTE if self._hover else style.HAIRLINE))
        p.setBrush(QColor(style.SURFACE if self._hover else style.GROUND_RAISED))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 14, 14)
        tile = QColor(style.accent())
        tile.setAlpha(40)
        p.setPen(Qt.NoPen)
        p.setBrush(tile)
        p.drawRoundedRect(QRectF(16, (h - 36) / 2, 36, 36), 10, 10)
        ink = QColor(style.accent()).darker(130) if not style.is_dark() else QColor(style.accent())
        draw(p, self._icon, QRectF(25, (h - 18) / 2, 18, 18), ink, 1.7)
        p.setPen(QColor(style.INK))
        p.setFont(style.font(style.BODY, QFont.Weight.DemiBold))
        p.drawText(QRectF(66, 14, w - 80, 22), Qt.AlignLeft | Qt.AlignVCenter, self._title)
        p.setPen(QColor(style.INK_MUTE))
        p.setFont(style.font(style.SMALL))
        desc = p.fontMetrics().elidedText(self._desc, Qt.ElideRight, int(w - 80))
        p.drawText(QRectF(66, 37, w - 80, 22), Qt.AlignLeft | Qt.AlignVCenter, desc)


#: The empty chat's suggestions: (icon, title, description, kind, payload).
#: kind "attach" opens the file picker and then starts the message; "prefill"
#: starts the message for you to finish; "send" runs a prompt that has been
#: verified end-to-end on Windows (a first suggestion that fails is worse
#: than none — it decides whether someone believes the rest).
SUGGESTIONS = (
    ("doc", "Explain a PDF", "Add your notes, then ask anything",
     "attach", "Explain the key ideas in this simply, then quiz me on them."),
    ("sigma", "Solve step by step", "Maths and physics, worked out",
     "prefill", "Solve this step by step and explain each step: "),
    ("code", "Fix my code", "Paste it along with the error",
     "prefill", "Here's my code and the error it gives. What's wrong?\n\n"),
    ("cursor", "Do it on my computer", "“Open YouTube” — and he does",
     "send", "open youtube.com"),
)


class _Hero(QWidget):
    """The empty chat: who Mike is, and something to start with."""

    suggestion = Signal(str, str)   # kind, payload

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addStretch(3)

        self.mark = PresenceMark(52)
        col.addWidget(self.mark, 0, Qt.AlignHCenter)
        col.addSpacing(18)

        self._title = QLabel()
        self._title.setFont(style.font(style.DISPLAY, QFont.Weight.DemiBold))
        self._title.setAlignment(Qt.AlignHCenter)
        self._title.setStyleSheet(f"color:{style.INK};background:transparent;")
        col.addWidget(self._title)
        col.addSpacing(8)

        self._sub = QLabel()
        self._sub.setWordWrap(True)
        self._sub.setFont(style.font(style.READ))
        self._sub.setAlignment(Qt.AlignHCenter)
        self._sub.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
        col.addWidget(_centred(self._sub, 560))
        col.addSpacing(28)

        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for i, (icon, title, desc, kind, payload) in enumerate(SUGGESTIONS):
            card = _Suggestion(icon, title, desc)
            card.clicked.connect(lambda k=kind, p=payload: self.suggestion.emit(k, p))
            grid.addWidget(card, i // 2, i % 2)
        col.addWidget(_centred(grid_holder, 640))
        col.addSpacing(22)

        self._hint = QLabel()
        self._hint.setFont(style.font(style.CAPTION))
        self._hint.setAlignment(Qt.AlignHCenter)
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
        col.addWidget(_centred(self._hint, 640))
        col.addStretch(4)

    _wake_listening = False

    def set_wake_listening(self, on: bool) -> None:
        self._wake_listening = bool(on)
        self.refresh_hint()

    def refresh_hint(self) -> None:
        hints = [f"{_hotkey_hint()} brings Mike from any app", "F6 to talk"]
        # only offered when the wake word is really running here, not merely
        # switched on — a hint that doesn't work is worse than none
        if self._wake_listening:
            hints.append("or just say “Hey Mike”")
        self._hint.setText("   ·   ".join(hints))

    def refresh(self) -> None:
        """Greet by the time of day and name — read fresh each time it shows."""
        from config import preferences

        first_run = not bool(preferences.get("onboarding_complete", False))
        name = str(preferences.get("profile_name", "") or "").strip()
        if first_run:
            self._title.setText("Hi, I'm Mike.")
            self._sub.setText(
                f"I live on {_this_machine()} and can actually use it — open things, "
                "find and write files, read your screen, fix code. I check before "
                "changing anything, and nothing leaves this machine.")
            preferences.set_value("onboarding_complete", True)
        else:
            h = datetime.now().hour
            part = ("Good morning" if 5 <= h < 12 else "Good afternoon"
                    if 12 <= h < 17 else "Good evening" if 17 <= h < 22 else "Still up")
            self._title.setText(f"{part}, {name}." if name else f"{part}.")
            self._sub.setText("What are we working on?")
        self.refresh_hint()


class ChatPage(QWidget):

    state_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state = "idle"
        self._stream: _RichTurn | None = None
        self._ledger: StepsCard | None = None
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

        # ── an empty chat's greeting, or the conversation ──
        self._views = QStackedWidget()
        outer.addWidget(self._views, 1)

        self._hero = _Hero()
        self._hero.suggestion.connect(self._on_suggestion)
        self._views.addWidget(self._hero)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("stage")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)

        column = QWidget()
        self._stage = QVBoxLayout(column)
        self._stage.setContentsMargins(0, 28, 0, 20)
        self._stage.setSpacing(20)
        self._stage.addStretch(1)
        self._scroll.setWidget(_centred(column))
        self._views.addWidget(self._scroll)

        self.conversation = _FollowingScroll(self._scroll)
        self.activity = _ActivityFacade()

        # ── the composer: confirm + input, along the bottom ──
        dock = QWidget()
        dcol = QVBoxLayout(dock)
        dcol.setContentsMargins(0, 6, 0, 18)
        dcol.setSpacing(10)

        self.confirm = ConfirmCard()
        self.confirm.visibility_changed.connect(
            lambda: QTimer.singleShot(0, self.conversation.scroll_to_bottom))
        dcol.addWidget(self.confirm)

        self.input = Composer()
        self.input.attach_requested.connect(self.add_attachments)
        self.input.attachment_removed.connect(self._remove_attachment)
        self.input.stop_requested.connect(self.activity.stop_requested.emit)
        dcol.addWidget(self.input)
        outer.addWidget(_centred(dock))

        self.setAcceptDrops(True)
        self._show_resting()

    # ── resting / greeting ────────────────────────────────
    def _show_resting(self) -> None:
        self._hero.refresh()
        self._views.setCurrentWidget(self._hero)

    def _show_stage(self) -> None:
        if self._views.currentWidget() is not self._scroll:
            self._views.setCurrentWidget(self._scroll)

    def _drop_resting(self) -> None:
        self._show_stage()

    def is_resting(self) -> bool:
        return self._views.currentWidget() is self._hero

    def _on_suggestion(self, kind: str, payload: str) -> None:
        if kind == "send":
            self.conversation.suggestion_clicked.emit(payload)
        elif kind == "attach":
            before = len(self._attachments)
            self.input._pick_files()
            if len(self._attachments) > before:
                self.input.set_text(payload)
        else:
            self.input.set_text(payload)

    # ── column helpers ────────────────────────────────────
    def _insert(self, widget: QWidget, animate: bool = True, force_scroll: bool = False) -> None:
        self._show_stage()
        self._stage.insertWidget(self._stage.count() - 1, widget)
        if animate and not style.reduced_motion():
            _animate_entry(widget)
        self.conversation.scroll_to_bottom(force=force_scroll)

    def _mike_turn(self, text: str) -> _RichTurn:
        return _RichTurn(text)

    # ── controller contract: conversation ─────────────────
    def add_user_message(self, text: str, attachments: list[str] | None = None) -> None:
        self._insert(_UserBubble(text, attachments), force_scroll=True)
        self._ledger = None

    def begin_mike_stream(self) -> _RichTurn:
        # The answer arriving means the steps before it are finished; if Mike
        # goes on to take another step, the card simply comes back to life.
        if self._ledger is not None and not self._ledger._settled and not self._ledger.is_running():
            self._ledger.settle("done")
        self._stream = self._mike_turn("")
        self._insert(self._stream)
        return self._stream

    def add_mike_message(self, text: str) -> None:
        self._insert(self._mike_turn(text))

    def add_notice(self, text: str, kind: str = "error") -> None:
        """An error Mike hit, or a note that you stopped him — shown as what it
        is rather than dressed up as something Mike said."""
        self._insert(_Notice(text, kind))

    def add_action_card(self, text: str) -> _ActionHandle:
        if self._ledger is None:
            self._ledger = StepsCard()
            self._insert(self._ledger)
        index = self._ledger.add_row(text)
        self.set_state("working")
        return _ActionHandle(self._ledger, index, text)

    def mark_stopped(self) -> None:
        """The user stopped Mike: whatever step was running didn't finish."""
        if self._ledger is not None:
            self._ledger.settle("stopped")

    def _live_card(self) -> StepsCard | None:
        """The steps card, if it's the latest thing in the chat and still live."""
        if self._ledger is None or self._ledger._settled:
            return None
        last = self._stage.itemAt(self._stage.count() - 2)
        return self._ledger if last is not None and last.widget() is self._ledger else None

    def show_thinking(self) -> None:
        self.hide_thinking()
        card = self._live_card()
        if card is not None:
            # between steps: the card itself says Mike is on it, so nothing
            # appears and vanishes underneath it
            card.set_thinking(True)
            return
        self._thinking = ThinkingLine(size=style.READ)
        self._insert(self._thinking)
        self._thinking.start()

    def hide_thinking(self) -> None:
        if self._ledger is not None:
            self._ledger.set_thinking(False)
        if self._thinking is not None:
            self._thinking.stop()
            self._thinking.hide()
            self._stage.removeWidget(self._thinking)
            self._thinking.deleteLater()
            self._thinking = None

    #: States that mean the turn is over, so its steps card can settle.
    _TURN_OVER = ("idle", "speaking", "error", "done")

    def set_state(self, state: str) -> None:
        self._state = state
        self.input.voice.set_state(state)
        self.input.set_listening(state == "listening")
        self.input.set_responding(
            state in ("thinking", "working", "responding", "speaking"))
        if self._ledger is not None and not self._ledger._settled:
            if state in self._TURN_OVER:
                self._ledger.settle("done")
            else:
                self._ledger.set_waiting(state == "needs_user")
        self._hero.mark.set_state(state)
        self.state_changed.emit(state)

    def state(self) -> str:
        return self._state

    def _clear_stage(self) -> None:
        self.hide_thinking()
        while self._stage.count() > 1:
            item = self._stage.takeAt(0)
            w = item.widget()
            if w is not None:
                # Hidden now, not just scheduled for deletion: a detached widget
                # stays painted at its old place until the deferred delete runs,
                # which showed the old chat under the new one.
                w.hide()
                w.deleteLater()
        self._stream = None
        self._ledger = None

    def clear(self) -> None:
        self._clear_stage()
        self._show_resting()
        self.set_state("idle")

    def show_conversation(self, turns: list[dict]) -> None:
        """Lay a saved conversation back out, exactly as it was said."""
        self._clear_stage()
        if not turns:
            self._show_resting()
            return
        self._show_stage()
        for t in turns:
            if t.get("role") == "user":
                self._insert(_UserBubble(t.get("content", ""), t.get("attachments")),
                             animate=False)
            elif t.get("role") == "assistant":
                self._insert(self._mike_turn(t.get("content", "")), animate=False)
        QTimer.singleShot(50, lambda: self.conversation.scroll_to_bottom(force=True))

    # ── attachments ───────────────────────────────────────
    def add_attachments(self, paths: list[str]) -> None:
        for path in paths:
            if path and os.path.exists(path) and path not in self._attachments:
                self._attachments.append(path)
        self.input.set_attachments(self._attachments)

    def take_attachments(self) -> list[str]:
        pending = list(self._attachments)
        self._attachments.clear()
        self.input.set_attachments(self._attachments)
        return pending

    def _remove_attachment(self, path: str) -> None:
        if path in self._attachments:
            self._attachments.remove(path)
        self.input.set_attachments(self._attachments)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_attachments(paths)
            event.acceptProposedAction()
