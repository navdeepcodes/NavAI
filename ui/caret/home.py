"""D3 — Home. Where the user dwells with Mike.

A typeset page, not a dashboard. One reading column on a near-black ground,
the two registers telling a claim apart from a fact, and a caret in the margin
that rides down beside whatever is happening now.

The thread is anchored to the bottom, growing up out of the composer, so the
surface is never a field of empty ground with a greeting floated in it.

Implements the method contract UIController already calls, so the frozen
runtime drives this surface unchanged.
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

from brain import activity_store
from config import preferences
from logs.logger import logger
from ui.caret import tokens
from ui.caret.caret import Caret
from ui.caret.text import Machine, Prose

GUTTER = 36          # the margin the caret lives in
RULE = "#232A38"     # slightly lifted hairline, so a rule reads as a rule


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
    """The composer caret is the mic. Clicking Mike is how you start talking."""

    clicked_voice = Signal()

    def __init__(self, composer: "Composer") -> None:
        super().__init__()
        self._composer = composer

    def set_state(self, state: str) -> None:
        self._composer.set_voice_state(state)


# ══ Column blocks ══════════════════════════════════════════

class Block(QWidget):
    """
    One thing in the thread, indented past the caret margin. Mike's own
    blocks carry a caret in that margin; the user's do not.
    """

    def __init__(self, content: QWidget, mike: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        margin = QWidget()
        margin.setFixedWidth(GUTTER)
        margin.setStyleSheet("background: transparent;")
        self.caret: Caret | None = None

        if mike:
            hold = QVBoxLayout(margin)
            hold.setContentsMargins(0, 0, 0, 0)
            hold.setSpacing(0)
            self.caret = Caret(5, 24)
            hold.addWidget(self.caret, 0, Qt.AlignLeft | Qt.AlignTop)
            hold.addStretch(1)

        row.addWidget(margin, 0, Qt.AlignTop)
        row.addWidget(content, 1)

        self.content = content

    def set_caret_visible(self, visible: bool) -> None:
        if self.caret is not None:
            self.caret.setVisible(visible)


class MachineBlock(QFrame):
    """
    A run of things Mike actually did. Rows appear as tools start and are
    recoloured when they finish — there is never a row for an action that has
    not begun, because the runtime cannot know one.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"border: none; border-left: 1px solid {RULE};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 1, 0, 1)
        layout.setSpacing(0)

        self._body = Machine("", size=12)
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
        tone = {
            "running": tokens.TEXT,
            "done": tokens.MUTED,
            "failed": tokens.RED,
        }
        lines = [
            f'<span style="color:{tone.get(status, tokens.MUTED)}">{text}</span>'
            for text, status in self._rows
        ]
        self._body.setTextFormat(Qt.RichText)
        self._body.setText(
            f'<div style="line-height:176%; font-family:{tokens.mono_family()}; '
            f'font-size:12px;">{"<br>".join(lines)}</div>'
        )


class _ActionHandle:
    def __init__(self, block: MachineBlock, index: int, text: str) -> None:
        self._block = block
        self._index = index
        self._label = _Label(text)

    def mark_done(self, success: bool = True) -> None:
        self._block.set_status(self._index, "done" if success else "failed")


# ══ Confirmation ═══════════════════════════════════════════

class ConfirmStrip(QFrame):
    """The safety gate, inline. Amber, and the only still caret in the product."""

    approved = Signal()
    denied = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 22, 0, 20)
        outer.setSpacing(0)

        # The still amber caret stands in the margin where Mike's caret would
        # otherwise be riding — Mike has stopped, and this is what that looks like.
        margin = QWidget()
        margin.setFixedWidth(GUTTER)
        margin.setStyleSheet("background: transparent;")
        hold = QVBoxLayout(margin)
        hold.setContentsMargins(0, 0, 0, 0)
        self.caret = Caret(5, 24)
        self.caret.set_state("needs_user")
        hold.addWidget(self.caret, 0, Qt.AlignLeft | Qt.AlignTop)
        hold.addStretch(1)
        outer.addWidget(margin, 0, Qt.AlignTop)

        body = QFrame()
        body.setStyleSheet(f"border: none; border-left: 1px solid {tokens.AMBER};")
        outer.addWidget(body, 1)

        row = QHBoxLayout(body)
        row.setContentsMargins(15, 6, 0, 6)
        row.setSpacing(0)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(9)

        self._what = Machine("", size=12, colour=tokens.TEXT)
        column.addWidget(self._what)

        keys = QHBoxLayout()
        keys.setSpacing(18)
        self._allow = self._key("\u23ce allow", tokens.AMBER)
        self._deny = self._key("esc deny", tokens.MUTED)
        self._allow.mousePressEvent = lambda e: self.approved.emit()
        self._deny.mousePressEvent = lambda e: self.denied.emit()
        keys.addWidget(self._allow)
        keys.addWidget(self._deny)
        keys.addStretch(1)
        column.addLayout(keys)

        row.addLayout(column, 1)
        self.hide()

    def _key(self, text: str, colour: str) -> QLabel:
        label = QLabel(text)
        label.setFont(tokens.machine(11))
        label.setStyleSheet(f"color: {colour}; background: transparent; border: none;")
        label.setCursor(Qt.PointingHandCursor)
        return label

    def ask(self, description: str) -> None:
        self._what.set_text(" ".join(description.split()))
        self.show()


# ══ Composer ═══════════════════════════════════════════════

class Composer(QFrame):
    """One line. No send button, no mic icon, no pill. Return submits."""

    submitted = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("composer")
        self.setStyleSheet(
            f"QFrame#composer {{ background: transparent; border: none;"
            f" border-top: 1px solid {RULE}; }}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 16, 0, 0)
        row.setSpacing(0)

        margin = QWidget()
        margin.setFixedWidth(GUTTER)
        margin.setStyleSheet("background: transparent;")
        hold = QHBoxLayout(margin)
        hold.setContentsMargins(0, 0, 0, 0)
        self.caret = Caret(tokens.CARET_W, tokens.CARET_H, clickable=True)
        self.caret.set_state("responding")
        hold.addWidget(self.caret, 0, Qt.AlignLeft | Qt.AlignVCenter)
        hold.addStretch(1)
        row.addWidget(margin, 0)

        self.field = QLineEdit()
        self.field.setPlaceholderText("Ask, or just talk")
        self.field.setFont(tokens.prose(15))
        self.field.setFrame(False)
        self.field.returnPressed.connect(self._submit)
        self.field.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent; border: none;
                color: {tokens.TEXT};
                selection-background-color: {tokens.HAIRLINE_LIT};
                padding: 0;
            }}
            """
        )
        row.addWidget(self.field, 1)

        self.hint = QLabel("⌘⇧space")
        self.hint.setFont(tokens.machine(11))
        self.hint.setStyleSheet(
            f"color: {tokens.FAINT}; background: transparent; border: none;"
        )
        row.addWidget(self.hint, 0, Qt.AlignVCenter)

        self.voice = _Voice(self)

    def _submit(self) -> None:
        text = self.field.text().strip()
        if text:
            self.field.clear()
            self.submitted.emit(text)

    def set_voice_state(self, state: str) -> None:
        self.caret.set_state(
            {"recording": "listening", "transcribing": "thinking"}
            .get(state, "responding")
        )

    def set_enabled(self, enabled: bool) -> None:
        self.field.setEnabled(enabled)
        self.field.setPlaceholderText("Ask, or just talk" if enabled else "")

    def focus(self) -> None:
        self.field.setFocus()


# ══ Home ═══════════════════════════════════════════════════

class HomeSurface(QWidget):
    """D3. Opens into the last exchange, because Mike is continuous."""

    ROOMS = ("Now", "Record", "Conduct")

    # Sized from real font metrics: ~74 characters of prose at 17px, which
    # is the measure, not a fraction of whatever window it lands in.
    COLUMN_MIN = 496
    COLUMN_MAX = 536

    def __init__(self, settings_hooks: dict | None = None) -> None:
        super().__init__()

        self._hooks = settings_hooks if settings_hooks is not None else {}
        self._state = "idle"
        self._machine_block: MachineBlock | None = None
        self._stream: Prose | None = None
        self._active: Block | None = None
        self._resting: Block | None = None
        self._last_app = ""
        self._room = "Now"

        self._build()
        self._show_resting()

        self._rail_timer = QTimer(self)
        self._rail_timer.setInterval(4000)
        self._rail_timer.timeout.connect(self._refresh_rail)
        self._rail_timer.start()
        self._refresh_rail()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._column.setFixedWidth(
            min(self.COLUMN_MAX, max(self.COLUMN_MIN, int(self.width() * 0.36)))
        )

    # ── Build ────────────────────────────────────────────

    def _build(self) -> None:
        self.setStyleSheet(f"background: {tokens.GROUND};")

        root = QHBoxLayout(self)
        root.setContentsMargins(tokens.GUTTER, 0, tokens.GUTTER, 0)
        root.setSpacing(0)
        root.addStretch(1)

        self._column = QWidget()
        self._column.setFixedWidth(self.COLUMN_MIN)
        self._column.setStyleSheet("background: transparent;")
        column = QVBoxLayout(self._column)
        column.setContentsMargins(0, 30, 0, 30)
        column.setSpacing(0)

        column.addWidget(self._build_rail())

        self._rooms_stack = QStackedLayout()
        self._rooms_stack.addWidget(self._build_now())
        self._rooms_stack.addWidget(self._build_record())
        self._rooms_stack.addWidget(self._build_conduct())
        column.addLayout(self._rooms_stack, 1)

        self.confirm = ConfirmStrip()
        column.addWidget(self.confirm)

        self.input = Composer()
        column.addWidget(self.input)

        column.addWidget(self._build_rooms())

        root.addWidget(self._column)
        root.addStretch(1)

        self.conversation = _Conversation(self)
        self.activity = _Activity()

    def _build_rail(self) -> QWidget:
        """Machine facts about this moment. Aligned to the column, not the window."""

        rail = QWidget()
        rail.setStyleSheet("background: transparent;")
        row = QHBoxLayout(rail)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(20)

        self._rail_left = QLabel("")
        self._rail_right = QLabel("")
        for label, colour, align in (
            (self._rail_left, tokens.MUTED, Qt.AlignLeft),
            (self._rail_right, tokens.FAINT, Qt.AlignRight),
        ):
            label.setFont(tokens.machine(11))
            label.setStyleSheet(
                f"color: {colour}; background: transparent; border: none;"
            )
            label.setAlignment(align | Qt.AlignVCenter)

        row.addWidget(self._rail_left, 1)
        row.addWidget(self._rail_right, 0)
        return rail

    def _build_now(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.setStyleSheet(self._scroll_css())

        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self._thread = QVBoxLayout(holder)
        self._thread.setContentsMargins(0, 34, 10, 26)
        self._thread.setSpacing(0)
        # The thread grows up out of the composer rather than down from the
        # top, so an empty or short session is never a field of dead ground.
        self._thread.addStretch(1)

        self._scroll.setWidget(holder)
        outer.addWidget(self._scroll, 1)
        return page

    def _scroll_css(self) -> str:
        return f"""
            QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
                background: transparent; border: none;
            }}
            QScrollBar:vertical {{ background: transparent; width: 7px; margin: 0; }}
            QScrollBar::handle:vertical {{
                background: {tokens.HAIRLINE_LIT}; border-radius: 3px; min-height: 30px;
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        """

    def _build_record(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 52, 0, 26)
        layout.setSpacing(0)

        self._record_scroll = QScrollArea()
        self._record_scroll.setWidgetResizable(True)
        self._record_scroll.setFrameShape(QFrame.NoFrame)
        self._record_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._record_scroll.viewport().setAutoFillBackground(False)
        self._record_scroll.setStyleSheet(self._scroll_css())

        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self._record_body = QVBoxLayout(holder)
        self._record_body.setContentsMargins(0, 0, 10, 0)
        self._record_body.setSpacing(0)
        self._record_scroll.setWidget(holder)

        layout.addWidget(self._record_scroll, 1)
        return page

    def _build_conduct(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 52, 0, 26)
        layout.setSpacing(0)

        self._conduct_body = QVBoxLayout()
        self._conduct_body.setSpacing(0)
        layout.addLayout(self._conduct_body)
        layout.addStretch(1)
        return page

    def _build_rooms(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background: transparent;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(GUTTER, 30, 0, 0)
        row.setSpacing(24)

        self._room_labels: dict[str, QLabel] = {}
        for name in self.ROOMS:
            label = QLabel(name.upper())
            label.setFont(tokens.machine(10))
            label.setCursor(Qt.PointingHandCursor)
            label.mousePressEvent = lambda event, n=name: self.show_room(n)
            self._room_labels[name] = label
            row.addWidget(label)

        row.addStretch(1)
        self._paint_rooms()
        return bar

    def _paint_rooms(self) -> None:
        for name, label in self._room_labels.items():
            active = name == self._room
            label.setStyleSheet(
                f"color: {tokens.TEXT if active else tokens.MUTED};"
                "background: transparent; border: none;"
                f"border-bottom: 1px solid "
                f"{tokens.INDIGO if active else 'transparent'};"
                "padding-bottom: 4px; letter-spacing: 1.2px;"
            )

    # ── The resting state ────────────────────────────────

    def _show_resting(self) -> None:
        """
        No greeting. One line of true machine facts about this session, so an
        untouched surface still says something rather than saying hello.
        """

        facts = []
        try:
            from brain.core_tools import TOOL_DECLARATIONS
            facts.append(f"{len(TOOL_DECLARATIONS)} tools")
        except Exception:
            pass
        try:
            from brain.core_runtime import OLLAMA_MODEL
            facts.insert(0, f"{OLLAMA_MODEL} · local")
        except Exception:
            facts.insert(0, "local")
        if preferences.get("wake_word_enabled", True):
            facts.append("listening for “Hey Mike”")

        line = Machine(" · ".join(facts), size=11.5, colour=tokens.FAINT)
        block = Block(line, mike=True)
        block.caret.set_state("idle")
        self._thread.addWidget(block)
        self._resting = block
        self._active = block

    def _drop_resting(self) -> None:
        if self._resting is not None:
            self._thread.removeWidget(self._resting)
            self._resting.deleteLater()
            self._resting = None

    # ── Rooms ────────────────────────────────────────────

    def show_room(self, name: str) -> None:
        if name not in self.ROOMS:
            return
        self._room = name
        self._rooms_stack.setCurrentIndex(self.ROOMS.index(name))
        self._paint_rooms()

        if name == "Record":
            self._fill_record()
        elif name == "Conduct":
            self._fill_conduct()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _fill_record(self) -> None:
        """Only what actually happened, read straight from the activity log."""

        self._clear_layout(self._record_body)

        rows = activity_store.recent(80)
        if not rows:
            self._record_body.addWidget(
                Machine("no actions recorded yet", size=12, colour=tokens.FAINT)
            )
            self._record_body.addStretch(1)
            return

        current_day = None
        for row in rows:
            when = datetime.fromtimestamp(row.get("started_at") or 0)
            day = when.strftime("%A %-d %B").upper()

            if day != current_day:
                current_day = day
                if self._record_body.count():
                    self._record_body.addSpacing(32)
                self._record_body.addWidget(
                    Machine(day, size=10, colour=tokens.FAINT)
                )
                self._record_body.addSpacing(14)

            block = QFrame()
            block.setStyleSheet(f"border: none; border-left: 1px solid {RULE};")
            inner = QVBoxLayout(block)
            inner.setContentsMargins(15, 2, 0, 2)
            inner.setSpacing(1)

            inner.addWidget(
                Machine(
                    f"{when.strftime('%H:%M')}   {row.get('action') or ''}",
                    size=12,
                    colour=tokens.DIM,
                )
            )

            outcome = (row.get("outcome") or "").strip()
            if outcome:
                ok = bool(row.get("succeeded"))
                inner.addWidget(
                    Machine(
                        f"      {' '.join(outcome.split())[:88]}",
                        size=11,
                        colour=tokens.FAINT if ok else tokens.RED,
                    )
                )

            self._record_body.addWidget(block)
            self._record_body.addSpacing(10)

        self._record_body.addStretch(1)

    def _fill_conduct(self) -> None:
        """Statements about Mike, not a control panel."""

        self._clear_layout(self._conduct_body)

        def heading(text: str) -> None:
            if self._conduct_body.count():
                self._conduct_body.addSpacing(36)
            self._conduct_body.addWidget(
                Machine(text.upper(), size=10, colour=tokens.FAINT)
            )
            self._conduct_body.addSpacing(15)

        def statement(text: str, value: str, key: str | None = None) -> None:
            holder = QWidget()
            holder.setStyleSheet("background: transparent;")
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(22)

            row.addWidget(Prose(text, size=15, colour=tokens.DIM), 1)

            right = QLabel(value)
            right.setFont(tokens.machine(11))
            right.setStyleSheet(
                f"color: {tokens.TEXT if key else tokens.MUTED};"
                "background: transparent; border: none;"
            )
            if key:
                right.setCursor(Qt.PointingHandCursor)
                right.mousePressEvent = lambda event, k=key: self._toggle(k)
            row.addWidget(right, 0, Qt.AlignTop)

            self._conduct_body.addWidget(holder)
            self._conduct_body.addSpacing(15)

        speaks = bool(preferences.get("voice_enabled", True))
        wakes = bool(preferences.get("wake_word_enabled", True))

        heading("Manner — how Mike behaves")
        statement("Speaks replies aloud", "on" if speaks else "off", "voice_enabled")
        statement("Wakes on “Hey Mike”", "on" if wakes else "off", "wake_word_enabled")

        heading("Limits — what Mike may do")
        statement("Always asks before writing, deleting or running anything", "architecture")
        statement("Reads the screen only when asked", "on request")

        heading("Reach — where Mike can act")
        try:
            from ide import manager as ide_manager
            connected = ide_manager.is_connected()
        except Exception:
            connected = False
        statement(
            "Editor bridge",
            "connected" if connected else "listening · 127.0.0.1:8787",
        )
        statement("Summoned from anywhere", "⌘⇧space")

        heading("Privacy")
        statement("Everything stays on this Mac", "no network calls")

    def _toggle(self, key: str) -> None:
        new_value = not bool(preferences.get(key, True))
        preferences.set(key, new_value)

        hook = {
            "voice_enabled": "on_voice_toggle",
            "wake_word_enabled": "on_wake_toggle",
        }.get(key)
        callback = self._hooks.get(hook) if hook else None
        if callable(callback):
            try:
                callback(new_value)
            except Exception:
                logger.exception("Conduct toggle failed for %s", key)

        self._fill_conduct()

    # ── Context rail ─────────────────────────────────────

    def _refresh_rail(self) -> None:
        try:
            self._rail_left.setText(self._where())
            self._rail_right.setText(self._today())
        except Exception:
            logger.exception("Home rail refresh failed.")

    def _where(self) -> str:
        try:
            from ide import manager as ide_manager
            if ide_manager.is_connected():
                context = ide_manager.get_context()
                if context is not None and context.filename:
                    editor = context.editor or "Editor"
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

        return self._last_app or datetime.now().strftime("%A %-d %B")

    def _today(self) -> str:
        clock = datetime.now().strftime("%H:%M")
        try:
            midnight = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            ).timestamp()
            count = sum(
                1 for row in activity_store.recent(200)
                if (row.get("started_at") or 0) >= midnight
            )
        except Exception:
            count = 0

        return f"{clock}   {count} actions today" if count else clock

    # ── Column composition ───────────────────────────────

    def _add_block(self, content: QWidget, mike: bool, gap: int = 0) -> Block:
        self._drop_resting()

        if gap and self._thread.count() > 1:
            self._thread.addSpacing(gap)

        block = Block(content, mike=mike)
        self._thread.addWidget(block)

        if mike:
            # Only the newest of Mike's blocks carries the caret — it rides
            # down the margin beside whatever is happening now.
            if self._active is not None and self._active is not block:
                self._active.set_caret_visible(False)
            self._active = block
            block.caret.set_state(self._state)

        QTimer.singleShot(0, self.scroll_to_bottom)
        return block

    # ── Controller contract ──────────────────────────────

    def add_user_message(self, text: str) -> None:
        said = QFrame()
        said.setStyleSheet(
            f"border: none; border-left: 1px solid {tokens.HAIRLINE_LIT};"
        )
        inner = QVBoxLayout(said)
        inner.setContentsMargins(15, 0, 0, 0)
        inner.addWidget(Prose(text, size=16, colour=tokens.DIM))

        self._add_block(said, mike=False, gap=36)
        self._machine_block = None
        self._stream = None
        self.show_room("Now")

    def add_action_card(self, text: str):
        if self._machine_block is None:
            self._machine_block = MachineBlock()
            self._add_block(self._machine_block, mike=True, gap=18)

        index = self._machine_block.add_row(text)
        self.set_state("working")
        return _ActionHandle(self._machine_block, index, text)

    def begin_mike_stream(self):
        self._stream = Prose("", size=17)
        self._add_block(self._stream, mike=True, gap=20)
        self._machine_block = None
        self.set_state("responding")
        return _Stream(self._stream)

    def add_mike_message(self, text: str) -> None:
        self._add_block(Prose(text, size=17), mike=True, gap=22)
        self._machine_block = None
        self._stream = None

    def show_tool_status(self, text: str) -> None:
        self.add_action_card(text)

    def show_thinking(self) -> None:
        self.set_state("thinking")

    def hide_thinking(self) -> None:
        if self._state == "thinking":
            self.set_state("idle")

    def clear(self) -> None:
        while self._thread.count() > 1:
            item = self._thread.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._machine_block = None
        self._stream = None
        self._active = None
        self._resting = None
        self._show_resting()
        self.set_state("idle")

    def scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ── State ────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        self._state = state
        if self._active is not None and self._active.caret is not None:
            # Only ever one caret: while the gate is up, the gate is Mike.
            self._active.set_caret_visible(state != "needs_user")
            self._active.caret.set_state(state)

    def state(self) -> str:
        return self._state

    # ── Overlays ─────────────────────────────────────────

    def showing_overlay(self) -> bool:
        return self._room != "Now"

    def close_overlays(self) -> None:
        self.show_room("Now")


class _Stream:
    def __init__(self, label: Prose) -> None:
        self._label = label

    def append_text(self, text: str) -> None:
        self._label.append_text(text)
