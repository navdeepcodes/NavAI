"""D3 — Home. The instrument housing, opened up.

Dark metal on the left: the dial, an honest trip counter, and three plain
switches — Chat, History, Settings. Paper logbook on the right: the actual
conversation, ink on cream, because a control-panel metaphor was never going
to hold real prose and pretending otherwise was the mistake in the first pass.

No legend anywhere here. The dial's meaning has to be self-evident from what
it does, not explained by a caption — that was true in the design study and
it's non-negotiable in the product.

Implements the same controller contract the frozen UIController already
drives, so nothing in brain/ or ui/controller moves.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from brain import activity_store, memory_store, revert_store
from config import preferences
from logs.logger import logger
from ui.instrument import tokens
from ui.instrument.dial import Dial
from ui.instrument.widgets import (
    Byline,
    Counter,
    EngravedLabel,
    Ink,
    InkFact,
    LogbookPage,
    MachineTicker,
)

RAIL_W = 190


# ══ Proxies the controller expects ═════════════════════════

class _Label:
    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


class _Conversation(QObject):
    suggestion_clicked = Signal(str)

    def __init__(self, page: "HomeSurface") -> None:
        super().__init__()
        self._page = page

    def scroll_to_bottom(self) -> None:
        self._page.scroll_to_bottom()


class _Activity(QObject):
    stop_requested = Signal()


class _Voice(QObject):
    clicked_voice = Signal()

    def __init__(self, composer: "Composer") -> None:
        super().__init__()
        self._composer = composer

    def set_state(self, state: str) -> None:
        self._composer.set_voice_state(state)


# ══ A run of tool calls, in the machine register ═══════════

class MachineBlock(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        self._body = InkFact("")
        layout.addWidget(self._body)
        self._rows: list[tuple[str, str]] = []

    def add_row(self, text: str) -> int:
        self._rows.append((text, "running"))
        self._render()
        return len(self._rows) - 1

    def set_status(self, index: int, status: str) -> None:
        if 0 <= index < len(self._rows):
            self._rows[index] = (self._rows[index][0], status)
            self._render()

    def _render(self) -> None:
        from html import escape as _esc

        tone = {"running": tokens.INK, "done": tokens.INK_DIM, "failed": tokens.RED}
        lines = [
            f'<span style="color:{tone.get(status, tokens.INK_DIM)}">{_esc(text)}</span>'
            for text, status in self._rows
        ]
        self._body.setTextFormat(Qt.RichText)
        self._body.setText(
            f'<div style="line-height:160%; color:{tokens.INK_DIM}; '
            f'font-family:{tokens.mono_family()}; font-size:11.5px;">'
            f'{"<br>".join(lines)}</div>'
        )


class _ActionHandle:
    def __init__(self, block: MachineBlock, index: int, text: str) -> None:
        self._block = block
        self._index = index
        self._label = _Label(text)

    def mark_done(self, success: bool = True) -> None:
        self._block.set_status(self._index, "done" if success else "failed")


# ══ Confirmation — the flag, made actionable ═══════════════

class ConfirmStrip(QFrame):
    approved = Signal()
    denied = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 10, 0, 10)
        row.setSpacing(14)

        column = QVBoxLayout()
        column.setSpacing(10)
        self._what = InkFact("")
        column.addWidget(self._what)

        keys = QHBoxLayout()
        keys.setSpacing(10)
        self._allow = self._switch("⏎  allow", allow=True)
        self._deny = self._switch("esc  deny", allow=False)
        self._allow.mousePressEvent = lambda e: self.approved.emit()
        self._deny.mousePressEvent = lambda e: self.denied.emit()
        keys.addWidget(self._allow)
        keys.addWidget(self._deny)
        keys.addStretch(1)
        column.addLayout(keys)

        row.addLayout(column, 1)
        self.hide()

    def _switch(self, text: str, allow: bool) -> QLabel:
        label = QLabel(text)
        label.setFont(tokens.label(11.5))
        if allow:
            label.setStyleSheet(
                f"background: qlineargradient(y1:0, y2:1, stop:0 #3A2A20, stop:1 #2A1D16);"
                f"border: 1px solid {tokens.RED}; color: {tokens.AMBER};"
                f"border-radius: 4px; padding: 7px 15px;"
            )
        else:
            label.setStyleSheet(
                f"background: qlineargradient(y1:0, y2:1, stop:0 #241F1A, stop:1 #1A1611);"
                f"border: 1px solid {tokens.HAIRLINE}; color: {tokens.MUTED};"
                f"border-radius: 4px; padding: 7px 15px;"
            )
        label.setCursor(Qt.PointingHandCursor)
        return label

    def ask(self, description: str) -> None:
        self._what.set_text(" ".join(description.split()))
        self.show()


# ══ Composer ═══════════════════════════════════════════════

class Composer(QFrame):
    submitted = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background: transparent; border: none; border-top: 1px solid {tokens.HAIRLINE};"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 14, 0, 0)
        row.setSpacing(12)

        self.dial = Dial(22)
        row.addWidget(self.dial, 0, Qt.AlignVCenter)

        self.field = QLineEdit()
        self.field.setPlaceholderText("Ask, or just talk")
        self.field.setFont(tokens.sans(14.5))
        self.field.setFrame(False)
        self.field.returnPressed.connect(self._submit)
        self.field.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent; border: none;
                color: {tokens.TEXT};
                selection-background-color: {tokens.HAIRLINE};
                padding: 0;
            }}
            """
        )
        row.addWidget(self.field, 1)

        self.hint = EngravedLabel("⌘⇧space", colour=tokens.FAINT, size=10)
        row.addWidget(self.hint, 0, Qt.AlignVCenter)

        self.voice = _Voice(self)

    def _submit(self) -> None:
        text = self.field.text().strip()
        if text:
            self.field.clear()
            self.submitted.emit(text)

    def set_voice_state(self, state: str) -> None:
        self.dial.set_state(
            {"recording": "listening", "transcribing": "thinking"}.get(state, "responding")
        )

    def set_enabled(self, enabled: bool) -> None:
        self.field.setEnabled(enabled)
        self.field.setPlaceholderText("Ask, or just talk" if enabled else "")

    def focus(self) -> None:
        self.field.setFocus()


# ══ Home ═══════════════════════════════════════════════════

class HomeSurface(QWidget):

    ROOMS = ("Chat", "History", "Settings")

    def __init__(self, settings_hooks: dict | None = None) -> None:
        super().__init__()

        self._hooks = settings_hooks if settings_hooks is not None else {}
        self._state = "idle"
        self._machine_block: MachineBlock | None = None
        self._task_reading_count = 0
        self._last_app = ""
        self._room = "Chat"

        self._build()
        self._refresh_counters()

        self._rail_timer = QTimer(self)
        self._rail_timer.setInterval(4000)
        self._rail_timer.timeout.connect(self._refresh_counters)
        self._rail_timer.start()

    # ── Build ────────────────────────────────────────────

    def _build(self) -> None:
        self.setStyleSheet(f"background: {tokens.GROUND};")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_rail())
        root.addWidget(self._divider())
        root.addWidget(self._build_body(), 1)

        self.conversation = _Conversation(self)
        self.activity = _Activity()

    def _divider(self) -> QWidget:
        line = QFrame()
        line.setFixedWidth(1)
        line.setStyleSheet(f"background: {tokens.HAIRLINE}; border: none;")
        return line

    def _build_rail(self) -> QWidget:
        rail = QWidget()
        rail.setFixedWidth(RAIL_W)
        rail.setStyleSheet("background: transparent;")
        col = QVBoxLayout(rail)
        col.setContentsMargins(24, 30, 24, 24)
        col.setSpacing(0)

        self.dial = Dial(104)
        col.addWidget(self.dial, 0, Qt.AlignHCenter)
        col.addSpacing(16)

        self.counter = Counter(0)
        col.addWidget(self.counter, 0, Qt.AlignHCenter)
        col.addSpacing(7)

        readings_lbl = EngravedLabel("readings today", size=9.5)
        col.addWidget(readings_lbl, 0, Qt.AlignHCenter)

        col.addStretch(1)

        self._context_lbl = EngravedLabel("", colour=tokens.MUTED, size=9.5)
        self._context_lbl.setWordWrap(True)
        col.addWidget(self._context_lbl)
        col.addSpacing(14)

        self._room_labels: dict[str, QLabel] = {}
        for name in self.ROOMS:
            label = QLabel(name)
            label.setFont(tokens.sans(12.5))
            label.setCursor(Qt.PointingHandCursor)
            label.mousePressEvent = lambda event, n=name: self.show_room(n)
            self._room_labels[name] = label
            col.addWidget(label)
            col.addSpacing(10)

        self._paint_rooms()
        return rail

    def _build_body(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(body)
        outer.setContentsMargins(28, 22, 28, 20)
        outer.setSpacing(0)

        self._context_top = EngravedLabel("", colour=tokens.MUTED, size=10)
        outer.addWidget(self._context_top)
        outer.addSpacing(16)

        self._stack = QStackedLayout()
        self._stack.addWidget(self._build_chat())
        self._stack.addWidget(self._build_history())
        self._stack.addWidget(self._build_settings())
        outer.addLayout(self._stack, 1)

        self.confirm = ConfirmStrip()
        outer.addWidget(self.confirm)

        self.input = Composer()
        outer.addWidget(self.input)

        return body

    # ── Chat (paper logbook) ──────────────────────────────

    def _build_chat(self) -> QWidget:
        page = LogbookPage()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.setStyleSheet(
            """
            QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {
                background: transparent; border: none;
            }
            QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
            QScrollBar::handle:vertical {
                background: rgba(42,38,32,.18); border-radius: 3px; min-height: 30px;
            }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
            """
        )

        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self._thread = QVBoxLayout(holder)
        self._thread.setContentsMargins(26, 22, 26, 18)
        self._thread.setSpacing(0)
        self._thread.addStretch(1)

        self._scroll.setWidget(holder)
        outer.addWidget(self._scroll)
        self._resting: QWidget | None = None
        self._show_resting()
        return page

    # Four true things, once, in Mike's own voice on the first page of his
    # own logbook — not a wizard, not a modal, gone the moment you use him.
    _INTRO_TEXT = (
        "I'm Mike — I live on this Mac, not in a browser tab. I stay running "
        "in the background, and nothing about this ever leaves this machine.\n\n"
        "I can read and write files, run terminal commands, use your browser, "
        "and look at your screen when you ask — but anything that actually "
        "changes something, I'll check with you first.\n\n"
        "I don't remember everything you say. Just what's worth keeping — "
        "and you can see exactly what, and forget any of it, any time, in History."
    )

    def _show_resting(self) -> None:
        """
        An unwritten logbook page isn't an empty void — it's a page with a
        date at the top and nothing on it yet. Same idea here, so idle Home
        never reads as a broken blank rectangle.

        On the very first launch, that first page carries a short, honest
        introduction instead of just a date — the one time Mike gets to say
        what he is before you start using him.
        """
        if self._resting is not None:
            return
        block = QWidget()
        block.setStyleSheet("background: transparent;")
        col = QVBoxLayout(block)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        date_lbl = QLabel(datetime.now().strftime("%A %-d %B").upper())
        date_lbl.setFont(tokens.label(10))
        date_lbl.setStyleSheet(f"color: {tokens.INK_DIM}; background: transparent; border: none;")
        col.addWidget(date_lbl)
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {tokens.PAPER_RULE}; border: none;")
        col.addWidget(rule)

        if not bool(preferences.get("onboarding_complete", False)):
            col.addSpacing(18)
            intro = Ink(self._INTRO_TEXT, size=15)
            col.addWidget(intro)
            col.addSpacing(14)
            hint = InkFact("⌘⇧space — from anywhere, any time")
            col.addWidget(hint)
            preferences.set_value("onboarding_complete", True)

        self._thread.insertWidget(0, block)
        self._resting = block

    def _drop_resting(self) -> None:
        if self._resting is not None:
            self._thread.removeWidget(self._resting)
            self._resting.deleteLater()
            self._resting = None

    HISTORY_TABS = ("Activity", "Memory")

    def _build_history(self) -> QWidget:
        """
        History is one room with two tabs, not two rooms — "what did Mike
        do" and "what does Mike know" are both the same "let me look back"
        motion for the user.
        """
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        tabs = QHBoxLayout()
        tabs.setSpacing(18)
        self._history_tab = "Activity"
        self._history_tab_labels: dict[str, QLabel] = {}
        for name in self.HISTORY_TABS:
            label = QLabel(name)
            label.setFont(tokens.sans(12))
            label.setCursor(Qt.PointingHandCursor)
            label.mousePressEvent = lambda event, n=name: self._show_history_tab(n)
            self._history_tab_labels[name] = label
            tabs.addWidget(label)
        tabs.addStretch(1)
        layout.addLayout(tabs)

        self._history_stack = QStackedLayout()
        self._history_stack.addWidget(self._build_activity_page())
        self._history_stack.addWidget(self._build_memory_page())
        layout.addLayout(self._history_stack, 1)

        self._paint_history_tabs()
        return page

    def _build_activity_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        self._history_scroll = QScrollArea()
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setFrameShape(QFrame.NoFrame)
        self._history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._history_scroll.viewport().setAutoFillBackground(False)
        self._history_scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget"
            "{ background: transparent; border: none; }"
        )
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self._history_body = QVBoxLayout(holder)
        self._history_body.setContentsMargins(0, 0, 10, 0)
        self._history_scroll.setWidget(holder)
        layout.addWidget(self._history_scroll)
        return page

    def _build_memory_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        self._memory_scroll = QScrollArea()
        self._memory_scroll.setWidgetResizable(True)
        self._memory_scroll.setFrameShape(QFrame.NoFrame)
        self._memory_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._memory_scroll.viewport().setAutoFillBackground(False)
        self._memory_scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget"
            "{ background: transparent; border: none; }"
        )
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self._memory_body = QVBoxLayout(holder)
        self._memory_body.setContentsMargins(0, 0, 10, 0)
        self._memory_scroll.setWidget(holder)
        layout.addWidget(self._memory_scroll)
        return page

    def _paint_history_tabs(self) -> None:
        for name, label in self._history_tab_labels.items():
            active = name == self._history_tab
            label.setStyleSheet(
                f"color: {tokens.TEXT if active else tokens.MUTED};"
                "background: transparent; border: none;"
                f"border-bottom: 1.5px solid {tokens.AMBER if active else 'transparent'};"
                "padding-bottom: 4px;"
            )

    def _show_history_tab(self, name: str) -> None:
        if name not in self.HISTORY_TABS:
            return
        self._history_tab = name
        self._history_stack.setCurrentIndex(self.HISTORY_TABS.index(name))
        self._paint_history_tabs()
        if name == "Activity":
            self._fill_history()
        elif name == "Memory":
            self._fill_memory()

    def _build_settings(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._settings_body = QVBoxLayout()
        self._settings_body.setSpacing(0)
        layout.addLayout(self._settings_body)
        layout.addStretch(1)
        return page

    def _paint_rooms(self) -> None:
        for name, label in self._room_labels.items():
            active = name == self._room
            label.setStyleSheet(
                f"color: {tokens.TEXT if active else tokens.MUTED};"
                "background: transparent; border: none;"
                f"border-left: 2px solid {tokens.AMBER if active else 'transparent'};"
                "padding-left: 10px;"
            )

    # ── Rooms ────────────────────────────────────────────

    def show_room(self, name: str) -> None:
        if name not in self.ROOMS:
            return
        self._room = name
        self._stack.setCurrentIndex(self.ROOMS.index(name))
        self._paint_rooms()
        if name == "History":
            self._show_history_tab(self._history_tab)
        elif name == "Settings":
            self._fill_settings()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _fill_history(self) -> None:
        self._clear_layout(self._history_body)
        rows = activity_store.recent(100)
        if not rows:
            empty = MachineTicker("Nothing recorded yet.", size=12, colour=tokens.MUTED)
            self._history_body.addWidget(empty)
            self._history_body.addStretch(1)
            return

        current_day = None
        for row in rows:
            when = datetime.fromtimestamp(row.get("started_at") or 0)
            day = when.strftime("%A %-d %B")
            if day != current_day:
                current_day = day
                if self._history_body.count():
                    self._history_body.addSpacing(24)
                self._history_body.addWidget(EngravedLabel(day, colour=tokens.FAINT, size=10))
                self._history_body.addSpacing(10)

            action = row.get("action") or ""
            line = MachineTicker(f"{when.strftime('%H:%M')}  {action}", size=12, colour=tokens.DIM)
            self._history_body.addWidget(line)

            outcome = (row.get("outcome") or "").strip()
            if outcome:
                ok = bool(row.get("succeeded"))
                self._history_body.addWidget(
                    MachineTicker(
                        f"      {' '.join(outcome.split())[:90]}",
                        size=11,
                        colour=tokens.MUTED if ok else tokens.RED,
                    )
                )

            snapshot = self._revert_snapshot(row.get("id"))
            if snapshot is not None:
                revert_lbl = QLabel("      ↺ revert this")
                revert_lbl.setFont(tokens.machine(11))
                revert_lbl.setStyleSheet(
                    f"color: {tokens.AMBER}; background: transparent; border: none;"
                )
                revert_lbl.setCursor(Qt.PointingHandCursor)
                revert_lbl.mousePressEvent = (
                    lambda event, sid=snapshot["id"]: self._revert_change(sid)
                )
                self._history_body.addWidget(revert_lbl)

            self._history_body.addSpacing(8)
        self._history_body.addStretch(1)

    def _revert_snapshot(self, activity_id) -> dict | None:
        if activity_id is None:
            return None
        try:
            return revert_store.for_activity(activity_id)
        except Exception:
            logger.exception("Could not check for a revert snapshot.")
            return None

    def _revert_change(self, snapshot_id: int) -> None:
        # A revert is itself an activity like any other Mike-performed
        # change — recorded the same way, so revert_store's own pre-revert
        # capture (see revert_store.revert) gets linked to a row the user
        # can find and, if this revert was itself a mistake, revert again.
        row_id = activity_store.begin("Reverting a change")
        try:
            result = revert_store.revert(snapshot_id)
        except Exception:
            logger.exception("Revert failed for snapshot %s", snapshot_id)
            result = {"status": "error", "error": "Something went wrong."}

        ok = result.get("status") == "success"
        outcome = result.get("result") if ok else result.get("error")
        activity_store.complete(row_id, outcome or "", ok)
        if ok and row_id is not None:
            revert_store.attach_to_activity(row_id)

        # Whatever happened, it's real — say so in the same machine register
        # as everything else here, then refresh so the row reflects it.
        self.add_mike_message(outcome or "Revert finished.")
        self._fill_history()

    # Plain-English section headers — the taxonomy in memory_store.py is
    # already the right shape, it just shouldn't say "workflow" out loud.
    _CATEGORY_HEADINGS = {
        "preference": "How you like things",
        "person": "People",
        "project": "Projects",
        "location": "Places",
        "workflow": "How you work",
        "fact": "Other things you've told him",
    }

    def _fill_memory(self) -> None:
        """
        A plain list, grouped by what kind of thing it is, in Mike's own
        words — not a database table. Reads straight from the live
        memory_store (the simple, keyword-based one) via all_memories();
        the more elaborate memory/ package is intentionally not used here.
        """
        self._clear_layout(self._memory_body)

        rows = memory_store.all_memories()
        if not rows:
            empty = QLabel(
                "Nothing yet. As you talk, Mike will remember the things "
                "worth carrying forward — you can always see the full list here."
            )
            empty.setFont(tokens.sans(13))
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color: {tokens.MUTED}; background: transparent; border: none;")
            self._memory_body.addWidget(empty)
            self._memory_body.addStretch(1)
            return

        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row.get("category") or "fact", []).append(row)

        order = ["person", "preference", "project", "workflow", "location", "fact"]
        categories = [c for c in order if c in grouped]
        categories += [c for c in grouped if c not in categories]

        for category in categories:
            if self._memory_body.count():
                self._memory_body.addSpacing(28)
            heading = self._CATEGORY_HEADINGS.get(category, category.title())
            self._memory_body.addWidget(EngravedLabel(heading, colour=tokens.FAINT, size=10))
            self._memory_body.addSpacing(12)

            for row in grouped[category]:
                self._memory_body.addWidget(self._memory_row(row))
                self._memory_body.addSpacing(14)

        self._memory_body.addStretch(1)

    def _memory_row(self, row: dict) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        outer = QHBoxLayout(holder)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        text = QLabel(row.get("content") or "")
        text.setFont(tokens.sans(14))
        text.setWordWrap(True)
        text.setStyleSheet(f"color: {tokens.DIM}; background: transparent; border: none;")
        outer.addWidget(text, 1)

        side = QVBoxLayout()
        side.setSpacing(6)

        when = datetime.fromtimestamp(row.get("created_at") or 0)
        date_lbl = QLabel(when.strftime("%-d %b"))
        date_lbl.setFont(tokens.machine(10.5))
        date_lbl.setStyleSheet(f"color: {tokens.FAINT}; background: transparent; border: none;")
        date_lbl.setAlignment(Qt.AlignRight)
        side.addWidget(date_lbl)

        forget = QLabel("forget")
        forget.setFont(tokens.machine(10.5))
        forget.setStyleSheet(f"color: {tokens.MUTED}; background: transparent; border: none;")
        forget.setAlignment(Qt.AlignRight)
        forget.setCursor(Qt.PointingHandCursor)
        memory_id = row.get("id")
        forget.mousePressEvent = lambda event, mid=memory_id: self._forget_memory(mid)
        side.addWidget(forget)

        outer.addLayout(side, 0)
        return holder

    def _forget_memory(self, memory_id: int | None) -> None:
        if memory_id is None:
            return
        try:
            memory_store.forget(memory_id=memory_id)
        except Exception:
            logger.exception("Failed to forget memory %s", memory_id)
        self._fill_memory()

    def _fill_settings(self) -> None:
        self._clear_layout(self._settings_body)

        def heading(text: str) -> None:
            if self._settings_body.count():
                self._settings_body.addSpacing(28)
            self._settings_body.addWidget(EngravedLabel(text, colour=tokens.FAINT, size=10))
            self._settings_body.addSpacing(12)

        def row(text: str, value: str, key: str | None = None) -> None:
            holder = QWidget()
            holder.setStyleSheet("background: transparent;")
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(20)

            left = QLabel(text)
            left.setFont(tokens.sans(14))
            left.setStyleSheet(f"color: {tokens.DIM}; background: transparent; border: none;")
            hl.addWidget(left, 1)

            right = QLabel(value)
            right.setFont(tokens.machine(11))
            right.setStyleSheet(
                f"color: {tokens.TEXT if key else tokens.MUTED}; background: transparent; border: none;"
            )
            if key:
                right.setCursor(Qt.PointingHandCursor)
                right.mousePressEvent = lambda event, k=key: self._toggle(k)
            hl.addWidget(right, 0)

            self._settings_body.addWidget(holder)
            self._settings_body.addSpacing(14)

        speaks = bool(preferences.get("voice_enabled", True))
        wakes = bool(preferences.get("wake_word_enabled", True))

        heading("How Mike behaves")
        row("Speaks replies aloud", "on" if speaks else "off", "voice_enabled")
        row("Wakes on “Hey Mike”", "on" if wakes else "off", "wake_word_enabled")

        heading("What Mike may do")
        row("Always asks before writing, deleting or running anything", "always")
        row("Reads the screen only when asked", "on request")

        heading("Where Mike can act")
        try:
            from ide import manager as ide_manager
            connected = ide_manager.is_connected()
        except Exception:
            connected = False
        row("Editor bridge", "connected" if connected else "listening · 127.0.0.1:8787")
        row("Summoned from anywhere", "⌘⇧space")

        heading("Privacy")
        row("Everything stays on this Mac", "no network calls")

    def _toggle(self, key: str) -> None:
        new_value = not bool(preferences.get(key, True))
        preferences.set_value(key, new_value)
        hook = {"voice_enabled": "on_voice_toggle", "wake_word_enabled": "on_wake_toggle"}.get(key)
        callback = self._hooks.get(hook) if hook else None
        if callable(callback):
            try:
                callback(new_value)
            except Exception:
                logger.exception("Settings toggle failed for %s", key)
        self._fill_settings()

    # ── Context + counters ────────────────────────────────

    def _refresh_counters(self) -> None:
        try:
            clock = datetime.now().strftime("%H:%M")
            midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            rows = activity_store.recent(300)
            count = sum(1 for r in rows if (r.get("started_at") or 0) >= midnight)
            self.counter.set_value(count)

            where = self._where()
            self._context_lbl.set_text(where)
            self._context_top.set_text(f"{where}  ·  {clock}")
        except Exception:
            logger.exception("Instrument rail refresh failed.")

    def _where(self) -> str:
        try:
            from ide import manager as ide_manager
            if ide_manager.is_connected():
                context = ide_manager.get_context()
                if context is not None and context.filename:
                    editor = context.editor or "editor"
                    if context.workspace_name:
                        return f"{editor} · {context.workspace_name}/{context.filename}"
                    return f"{editor} · {context.filename}"
        except Exception:
            pass
        try:
            from brain import environment
            app = environment._frontmost_app()
            if app and app not in ("Python", "Mike", "python3"):
                self._last_app = app
        except Exception:
            pass
        return self._last_app or datetime.now().strftime("%A")

    # ── Column composition ────────────────────────────────

    def _add_block(self, widget: QWidget, gap: int = 0) -> None:
        self._drop_resting()
        index = max(0, self._thread.count() - 1)
        if gap and index:
            self._thread.insertSpacing(index, gap)
            index += 1
        self._thread.insertWidget(index, widget)
        QTimer.singleShot(0, self.scroll_to_bottom)

    # ── Controller contract ───────────────────────────────

    def add_user_message(self, text: str) -> None:
        block = QWidget()
        block.setStyleSheet("background: transparent;")
        col = QVBoxLayout(block)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        col.addWidget(Byline("you"))
        col.addWidget(Ink(text, size=15))
        self._add_block(block, gap=22)
        self._machine_block = None
        self._task_reading_count = 0
        self.show_room("Chat")

    def add_action_card(self, text: str):
        if self._machine_block is None:
            self._machine_block = MachineBlock()
            self._add_block(self._machine_block, gap=10)
        index = self._machine_block.add_row(text)
        self._task_reading_count += 1
        self.set_state("working")
        return _ActionHandle(self._machine_block, index, text)

    def begin_mike_stream(self):
        block = QWidget()
        block.setStyleSheet("background: transparent;")
        col = QVBoxLayout(block)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        col.addWidget(Byline("mike"))
        ink = Ink("", size=15)
        col.addWidget(ink)
        self._add_block(block, gap=12)
        self._machine_block = None
        self.set_state("responding")
        return _Stream(ink)

    def add_mike_message(self, text: str) -> None:
        block = QWidget()
        block.setStyleSheet("background: transparent;")
        col = QVBoxLayout(block)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        col.addWidget(Byline("mike"))
        col.addWidget(Ink(text, size=15))
        self._add_block(block, gap=12)
        self._machine_block = None

    def show_tool_status(self, text: str) -> None:
        self.add_action_card(text)

    def show_thinking(self) -> None:
        self.set_state("thinking")

    def hide_thinking(self) -> None:
        if self._state == "thinking":
            self.set_state("idle")

    def clear(self) -> None:
        while self._thread.count() > 1:
            item = self._thread.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._machine_block = None
        self._resting = None
        self._show_resting()
        self.set_state("idle")

    def scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ── State ────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        self._state = state
        self.dial.set_state(state)
        self.input.dial.set_state(state if state != "idle" else "responding")

    def state(self) -> str:
        return self._state

    # ── Overlays ─────────────────────────────────────────

    def showing_overlay(self) -> bool:
        return self._room != "Chat"

    def close_overlays(self) -> None:
        self.show_room("Chat")


class _Stream:
    def __init__(self, ink: Ink) -> None:
        self._ink = ink

    def append_text(self, text: str) -> None:
        self._ink.append_text(text)
