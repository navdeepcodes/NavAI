"""Mike's surface: a summoned presence, exactly as large as the moment needs.

Not a window you live in. At rest it is a single input line with a quiet mark
of presence beside it. Ask something and it grows downward — your line, Mike's
reply, and, when Mike is actually doing work, an inline ledger of what he is
doing and whether it is going well. When it needs you, it says so, clearly and
unmistakably. Then it recedes.

This class implements exactly the contract UIController already calls
(add_user_message, begin_mike_stream, add_action_card, set_state, the input /
conversation / confirm / activity sub-objects and their signals), so the whole
engine underneath — brain, tools, voice, safety — is untouched. The redesign
lives entirely in how Mike presents himself.
"""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, QObject, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QKeyEvent
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mark import PresenceMark

STATE_WORD = {
    "idle": "", "listening": "Listening", "thinking": "Thinking",
    "working": "Working", "responding": "Responding", "speaking": "Speaking",
    "needs_user": "Needs you", "error": "Stopped", "done": "Done",
}


# ══ voice affordance ═══════════════════════════════════════

class _Voice(QWidget):
    clicked_voice = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.PointingHandCursor)
        self._state = "idle"

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def mousePressEvent(self, _e) -> None:
        self.clicked_voice.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        listening = self._state in ("listening",)
        colour = style.qaccent() if listening else QColor(style.INK_MUTE)
        p.setPen(Qt.NoPen)
        p.setBrush(colour)
        # a small, clean capsule — a microphone reduced to its essence
        p.drawRoundedRect(10, 5, 6, 11, 3, 3)
        from PySide6.QtGui import QPen
        arc = QPen(colour); arc.setWidthF(1.4); p.setPen(arc); p.setBrush(Qt.NoBrush)
        p.drawArc(7, 6, 12, 13, 200 * 16, 140 * 16)
        p.setPen(QPen(colour, 1.4))
        p.drawLine(13, 19, 13, 21)


# ══ input bar — the anchor ═════════════════════════════════

class _Field(QLineEdit):
    def __init__(self, on_submit, parent=None) -> None:
        super().__init__(parent)
        self._on_submit = on_submit

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_submit()
            return
        super().keyPressEvent(e)


class _InputBar(QFrame):
    submitted = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inputBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 11, 12, 11)
        row.setSpacing(10)

        self.voice = _Voice()
        row.addWidget(self.voice, 0, Qt.AlignVCenter)

        self._field = _Field(self._emit)
        self._field.setPlaceholderText("Ask Mike, or hold to talk")
        self._field.setFont(style.voice(14))
        self._field.setFrame(False)
        self._field.setStyleSheet(
            f"QLineEdit{{background:transparent;border:none;color:{style.INK};"
            f"selection-background-color:{style.accent()};}}"
            f"QLineEdit::placeholder{{color:{style.INK_MUTE};}}"
        )
        row.addWidget(self._field, 1)

        self._hint = QLabel("⌘⇧Space")
        self._hint.setFont(style.label(10))
        self._hint.setStyleSheet(f"color:{style.INK_FAINT};background:transparent;")
        row.addWidget(self._hint, 0, Qt.AlignVCenter)

    def _emit(self) -> None:
        text = self._field.text().strip()
        if text:
            self._field.clear()
            self.submitted.emit(text)

    def set_enabled(self, enabled: bool) -> None:
        self._field.setEnabled(enabled)
        self._field.setPlaceholderText(
            "Ask Mike, or hold to talk" if enabled else "Mike is working…")

    def focus(self) -> None:
        self._field.setFocus()

    def set_listening(self, on: bool) -> None:
        self._field.setPlaceholderText("Listening…" if on else "Ask Mike, or hold to talk")


# ══ streamed reply ═════════════════════════════════════════

class _Turn(QLabel):
    """A block of text — yours (quiet) or Mike's (primary)."""

    def __init__(self, text: str, who: str, parent=None) -> None:
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._who = who
        self._raw = text
        self._render()

    def _render(self) -> None:
        # Mike's speech is the hero: larger, warm-bright, generous line. Your
        # prompt is the quiet context that produced it — smaller, muted, marked
        # with a single accent tick. The contrast is the hierarchy; you scan
        # Mike's answers and the questions recede.
        if self._who == "mike":
            colour, size, lh, prefix = style.INK, 16, 164, ""
        else:
            colour, size, lh = style.INK_MUTE, 13, 150
            prefix = f'<span style="color:{style.accent()};">›</span>&nbsp;&nbsp;'
        self.setTextFormat(Qt.RichText)
        self.setText(
            f'<div style="color:{colour};font-family:{style.ui_family()};'
            f'font-size:{size}px;line-height:{lh}%;letter-spacing:0.1px;">{prefix}'
            f'{escape(self._raw).replace(chr(10), "<br>")}</div>'
        )

    def append_text(self, chunk: str) -> None:
        self._raw += chunk
        self._render()


# ══ activity ledger ════════════════════════════════════════

class _Ledger(QFrame):
    """What Mike is doing, as a short list with honest, living status marks.

    The step in flight isn't a static bullet — its mark breathes, so the panel
    reads as "Mike is doing something" rather than "a list that stopped
    updating." Completed steps settle to a quiet tick; a failure is a clear
    mark, not a colour the user has to decode. The pulse animates only while a
    step is actually running, and stops the moment the work is done.
    """

    _DONE = style.GOOD
    _FAILED = style.STOP

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ledger")
        col = QVBoxLayout(self)
        col.setContentsMargins(15, 13, 15, 13)
        col.setSpacing(0)
        self._body = QLabel()
        self._body.setWordWrap(True)
        col.addWidget(self._body)
        self._rows: list[tuple[str, str]] = []
        self._pulse = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._beat)

    def add_row(self, text: str) -> int:
        self._rows.append((text, "running"))
        self._sync_timer()
        self._render()
        return len(self._rows) - 1

    def set_status(self, index: int, status: str) -> None:
        if 0 <= index < len(self._rows):
            self._rows[index] = (self._rows[index][0], status)
            self._sync_timer()
            self._render()

    def _sync_timer(self) -> None:
        running = any(s == "running" for _, s in self._rows)
        if running and not self._timer.isActive():
            self._timer.start(1000 // 20)
        elif not running and self._timer.isActive():
            self._timer.stop()

    def _beat(self) -> None:
        import math
        self._pulse = 0.5 + 0.5 * math.sin(self._pulse_t())
        self._render()

    def _pulse_t(self) -> float:
        self._phase = getattr(self, "_phase", 0.0) + 0.16
        return self._phase * 3.0

    def _running_alpha(self) -> int:
        return int(150 + 105 * self._pulse)

    def _render(self) -> None:
        acc = style.qaccent()
        rows = []
        for text, status in self._rows:
            if status == "done":
                mark = f'<span style="color:{self._DONE};">✓</span>'
                tcol = style.INK_SOFT
            elif status == "failed":
                mark = f'<span style="color:{self._FAILED};">✕</span>'
                tcol = style.INK_SOFT
            else:
                a = self._running_alpha()
                mark = (f'<span style="color:rgba({acc.red()},{acc.green()},'
                        f'{acc.blue()},{a/255:.2f});">●</span>')
                tcol = style.INK
            rows.append(
                '<tr>'
                '<td style="font-size:11px;padding:3px 12px 3px 0;'
                'vertical-align:top;">' + mark + '</td>'
                f'<td style="color:{tcol};font-family:{style.ui_family()};'
                'font-size:13.5px;line-height:152%;padding:2px 0;">'
                + escape(text) + '</td></tr>'
            )
        self._body.setTextFormat(Qt.RichText)
        self._body.setText(
            '<table style="border-collapse:collapse;">' + "".join(rows) + '</table>')


class _ActionHandle:
    def __init__(self, ledger: _Ledger, index: int, text: str) -> None:
        self._ledger = ledger
        self._index = index
        self._label = _PlainText(text)

    def mark_done(self, success: bool = True) -> None:
        self._ledger.set_status(self._index, "done" if success else "failed")


class _PlainText:
    def __init__(self, text: str) -> None:
        self._t = text

    def text(self) -> str:
        return self._t


# ══ confirmation — a first-class, trustworthy moment ═══════

class _Confirm(QFrame):
    approved = Signal()
    denied = Signal()
    visibility_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("confirm")
        self.hide()
        col = QVBoxLayout(self)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(12)

        self._head = QLabel()
        self._head.setFont(style.label(10))
        self._head.setStyleSheet(
            f"color:{style.WARN};background:transparent;letter-spacing:1.5px;")
        col.addWidget(self._head)

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setFont(style.voice(14))
        self._body.setStyleSheet(f"color:{style.INK};background:transparent;")
        col.addWidget(self._body)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self._deny = QPushButton("Don't")
        self._deny.setObjectName("deny")
        self._deny.setCursor(Qt.PointingHandCursor)
        self._deny.clicked.connect(self.denied.emit)
        buttons.addWidget(self._deny)
        self._allow = QPushButton("Go ahead")
        self._allow.setObjectName("allow")
        self._allow.setCursor(Qt.PointingHandCursor)
        self._allow.clicked.connect(self.approved.emit)
        buttons.addWidget(self._allow)
        col.addLayout(buttons)

    def ask(self, description: str) -> None:
        self._head.setText("MIKE NEEDS YOU")
        self._body.setText(description)
        self.show()
        self.visibility_changed.emit()

    def hide(self) -> None:  # noqa: A003 - matches the controller contract
        super().hide()
        self.visibility_changed.emit()


# ══ thin façades the controller connects signals to ═══════

class _ConversationFacade(QObject):
    suggestion_clicked = Signal(str)

    def __init__(self, scroll: QScrollArea) -> None:
        super().__init__()
        self._scroll = scroll

    def scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))


class _ActivityFacade(QObject):
    stop_requested = Signal()


# ══ settings / memory / personalisation ═══════════════════

class _Swatch(QPushButton):
    def __init__(self, name: str, colour: str, on_pick) -> None:
        super().__init__()
        self._name = name
        self._colour = colour
        self._on_pick = on_pick
        self.setFixedSize(24, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(name.capitalize())
        self.clicked.connect(lambda: on_pick(name))
        self._selected = False

    def set_selected(self, on: bool) -> None:
        self._selected = on
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self._colour))
        p.drawEllipse(4, 4, 16, 16)
        if self._selected:
            from PySide6.QtGui import QPen
            pen = QPen(QColor(style.INK)); pen.setWidthF(1.5)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawEllipse(1, 1, 22, 22)


class _SettingsView(QScrollArea):
    closed = Signal()
    accent_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("settings")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        self._col = QVBoxLayout(body)
        self._col.setContentsMargins(20, 8, 20, 16)
        self._col.setSpacing(4)
        self.setWidget(body)
        self._swatches: list[_Swatch] = []

    def reload(self) -> None:
        while self._col.count():
            item = self._col.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._swatches.clear()

        top = QHBoxLayout()
        title = QLabel("MIKE")
        title.setFont(style.label(11))
        title.setStyleSheet(f"color:{style.INK_MUTE};letter-spacing:2px;background:transparent;")
        top.addWidget(title)
        top.addStretch(1)
        done = QPushButton("Done")
        done.setObjectName("deny")
        done.setCursor(Qt.PointingHandCursor)
        done.clicked.connect(self.closed.emit)
        top.addWidget(done)
        self._col.addLayout(top)
        self._col.addSpacing(6)

        self._section("APPEARANCE", "Mike's colour")
        row = QHBoxLayout(); row.setSpacing(10); row.setContentsMargins(0, 2, 0, 0)
        current = self._current_accent_name()
        for name, colour in style.accent_presets().items():
            sw = _Swatch(name, colour, self._pick_accent)
            sw.set_selected(name == current)
            self._swatches.append(sw)
            row.addWidget(sw)
        row.addStretch(1)
        holder = QWidget(); holder.setStyleSheet("background:transparent;"); holder.setLayout(row)
        self._col.addWidget(holder)
        self._col.addSpacing(14)

        self._section("VOICE", self._voice_line())
        self._col.addSpacing(14)
        self._section("MODEL", self._model_line())
        self._col.addSpacing(14)
        self._section("MEMORY", self._memory_line(), action=("Forget all", self._forget_all))
        self._col.addSpacing(14)
        self._section("PRIVACY", "Everything Mike does stays on this Mac. "
                      "No account, no cloud, nothing sent anywhere.")
        self._col.addStretch(1)

    def _section(self, label: str, detail: str, action=None) -> None:
        lbl = QLabel(label)
        lbl.setFont(style.label(9.5))
        lbl.setStyleSheet(f"color:{style.INK_FAINT};letter-spacing:1.5px;background:transparent;")
        self._col.addWidget(lbl)
        roww = QHBoxLayout(); roww.setContentsMargins(0, 2, 0, 0)
        text = QLabel(detail)
        text.setWordWrap(True)
        text.setFont(style.voice(13))
        text.setStyleSheet(f"color:{style.INK_SOFT};background:transparent;")
        roww.addWidget(text, 1)
        if action:
            btn = QPushButton(action[0])
            btn.setObjectName("deny")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(action[1])
            roww.addWidget(btn, 0, Qt.AlignTop)
        holder = QWidget(); holder.setStyleSheet("background:transparent;"); holder.setLayout(roww)
        self._col.addWidget(holder)

    # data
    def _current_accent_name(self) -> str:
        try:
            from config import preferences
            return str(preferences.get("accent", "amber") or "amber").lower()
        except Exception:
            return "amber"

    def _pick_accent(self, name: str) -> None:
        try:
            from config import preferences
            preferences.set_value("accent", name)
        except Exception:
            pass
        for sw in self._swatches:
            sw.set_selected(sw._name == name)
        self.accent_changed.emit()

    def _voice_line(self) -> str:
        try:
            from config import preferences
            p = str(preferences.get("voice_provider", "native")).lower()
            if p == "qwen":
                speaker = str(preferences.get("voice_qwen_speaker", "Ryan"))
                return f"{speaker} — a natural neural voice, running locally."
        except Exception:
            pass
        return "Samantha — the built-in system voice. Always available."

    def _model_line(self) -> str:
        try:
            from config.ollama import OLLAMA_CHAT_MODEL
            return f"Recommended for this Mac. Running {OLLAMA_CHAT_MODEL}, entirely on-device."
        except Exception:
            return "Running a local model, entirely on-device."

    def _memory_line(self) -> str:
        try:
            from brain import memory_store
            n = len(memory_store.all_memories(limit=500))
            if n == 0:
                return "Nothing kept yet. Mike remembers only what's worth keeping."
            return f"{n} thing{'s' if n != 1 else ''} kept — only what's worth remembering."
        except Exception:
            return "Mike remembers only what's worth keeping, and you control it."

    def _forget_all(self) -> None:
        try:
            from brain import memory_store
            memory_store.forget(query="everything")
        except Exception:
            pass
        self.reload()


# ══ the panel ══════════════════════════════════════════════

class MikePanel(QWidget):
    def __init__(self, settings_hooks: dict | None = None) -> None:
        super().__init__()
        self._hooks = settings_hooks or {}
        self._state = "idle"
        self._stream: _Turn | None = None
        self._ledger: _Ledger | None = None
        self._thinking: QWidget | None = None
        self._build()
        self.set_state("idle")

    # ── construction ──────────────────────────────────────
    SHADOW = 20   # room around the body for its drop shadow

    def _build(self) -> None:
        self.setAttribute(Qt.WA_StyledBackground, False)
        # translucent so only what the panel paints (shadow + body) shows; the
        # window behind it is translucent too, so the shadow composites over
        # the real desktop rather than a widget fill.
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        outer = QVBoxLayout(self)
        # margins leave room for the painted shadow so the panel lifts off the
        # desktop instead of sitting flat on it — lighter at the top edge
        # because the light comes from above.
        outer.setContentsMargins(self.SHADOW, self.SHADOW - 6, self.SHADOW, self.SHADOW)
        outer.setSpacing(0)

        # header: presence + state word, only as tall as it needs
        header = QWidget()
        hb = QHBoxLayout(header)
        hb.setContentsMargins(20, 15, 15, 9)
        hb.setSpacing(12)
        self.mark = PresenceMark(32)
        hb.addWidget(self.mark, 0, Qt.AlignVCenter)
        self._state_lbl = QLabel("")
        self._state_lbl.setFont(style.label(11))
        self._state_lbl.setStyleSheet(
            f"color:{style.INK_MUTE};background:transparent;letter-spacing:1.2px;")
        hb.addWidget(self._state_lbl, 1, Qt.AlignVCenter)
        self._stop = QPushButton("Stop")
        self._stop.setObjectName("stop")
        self._stop.setCursor(Qt.PointingHandCursor)
        self._stop.hide()
        self.activity = _ActivityFacade()
        self._stop.clicked.connect(self.activity.stop_requested.emit)
        hb.addWidget(self._stop, 0, Qt.AlignVCenter)

        self._menu_btn = QPushButton("⋯")
        self._menu_btn.setObjectName("menu")
        self._menu_btn.setCursor(Qt.PointingHandCursor)
        self._menu_btn.setFixedSize(28, 24)
        self._menu_btn.clicked.connect(self._toggle_settings)
        hb.addWidget(self._menu_btn, 0, Qt.AlignVCenter)
        outer.addWidget(header)

        # stage: the scrollable conversation + activity. Height follows content
        # up to a cap, then scrolls -- so a short exchange is a short panel and
        # only a long one grows, which is what keeps Mike from ever being a big
        # empty canvas.
        self._scroll = QScrollArea()
        self._scroll.setObjectName("stage")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setSizeAdjustPolicy(QScrollArea.AdjustToContents)
        stage = QWidget()
        stage.setStyleSheet("background:transparent;")
        self._stage = QVBoxLayout(stage)
        self._stage.setContentsMargins(18, 4, 18, 8)
        self._stage.setSpacing(14)
        self._stage.addStretch(1)
        self._scroll.setWidget(stage)
        outer.addWidget(self._scroll, 1)

        # the settings / memory / personalisation surface, summoned over the
        # stage rather than living as a separate window — everything about Mike
        # is reached from Mike, not from a menu bar.
        self._settings_view = _SettingsView()
        self._settings_view.closed.connect(self.close_overlays)
        self._settings_view.accent_changed.connect(self._restyle)
        self._settings_view.hide()
        outer.addWidget(self._settings_view, 1)

        self.conversation = _ConversationFacade(self._scroll)

        # confirmation slot (inline, above the input)
        self.confirm = _Confirm()
        self.confirm.visibility_changed.connect(lambda: QTimer.singleShot(0, self._fit))
        wrap = QVBoxLayout()
        wrap.setContentsMargins(14, 0, 14, 6)
        wrap.addWidget(self.confirm)
        outer.addLayout(wrap)

        # input: the anchor, always present
        self.input = _InputBar()
        pad = QVBoxLayout()
        pad.setContentsMargins(14, 4, 14, 14)
        pad.addWidget(self.input)
        outer.addLayout(pad)

        self.setStyleSheet(_build_stylesheet())
        self._show_resting()

    def _restyle(self) -> None:
        """Re-apply styles so a changed accent flows through the whole panel
        live — the presence mark already reads the accent on every paint."""
        self.setStyleSheet(_build_stylesheet())
        self.mark.update()
        self.input.voice.update()

    # ── resting composition ───────────────────────────────
    _INTRO = (
        "I'm Mike. I live on this Mac — not in a browser tab — and I stay here "
        "in the background. I can read and write files, run commands, use your "
        "browser and see your screen when you ask; anything that changes "
        "something, I check with you first. Nothing leaves this machine.\n\n"
        "Ask me anything below, or press ⌘⇧Space to talk from anywhere."
    )

    def _show_resting(self) -> None:
        from config import preferences

        first_run = not bool(preferences.get("onboarding_complete", False))
        text = self._INTRO if first_run else self._greeting()
        self._resting = _Turn(text, "mike")
        self._resting.setStyleSheet("padding-top:2px;")
        self._insert(self._resting)
        if first_run:
            preferences.set_value("onboarding_complete", True)

    def _greeting(self) -> str:
        from datetime import datetime
        h = datetime.now().hour
        part = ("Good morning." if 5 <= h < 12 else "Good afternoon."
                if 12 <= h < 17 else "Good evening." if 17 <= h < 22 else "Still here.")
        return f"{part}  Ask me anything, or press ⌘⇧Space to talk."

    def _drop_resting(self) -> None:
        r = getattr(self, "_resting", None)
        if r is not None:
            r.hide()
            self._stage.removeWidget(r)
            r.deleteLater()
            self._resting = None

    # ── sizing: the panel is as tall as its content, up to a cap ──────
    CAP_HEIGHT = 520
    HEADER_H = 52
    INPUT_H = 66

    STAGE_H_MARGIN = 36   # 18 left + 18 right
    SCROLLBAR_ALLOW = 12

    def _content_height(self) -> int:
        """The real height of the stage content at the panel's actual width.

        A word-wrapping QLabel reports a sizeHint that assumes a much narrower
        line than it will actually get, so summing sizeHints over-provisions
        the panel and leaves a dead band above the input -- the exact empty
        space the design must not have. Measuring each row with
        heightForWidth() at the true content width gives the height the text
        will really occupy.
        """
        stage = self._scroll.widget()
        if stage is None:
            return 0
        lay = stage.layout()
        margins = lay.contentsMargins()
        panel_w = self.width() if self.width() > 100 else 620
        width = panel_w - 2 * self.SHADOW - self.STAGE_H_MARGIN - self.SCROLLBAR_ALLOW
        total = margins.top() + margins.bottom()
        counted = 0
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if w is None:
                continue
            if w.hasHeightForWidth():
                h = w.heightForWidth(width)
            else:
                h = w.sizeHint().height()
            total += max(0, h)
            counted += 1
        total += lay.spacing() * max(0, counted - 1)
        return total

    def desired_height(self) -> int:
        conf = 0
        if self.confirm.isVisible():
            conf = self.confirm.sizeHint().height() + 12
        chrome = (self.SHADOW - 6) + self.SHADOW   # top + bottom shadow room
        stage_room = self.CAP_HEIGHT - self.HEADER_H - self.INPUT_H - conf - chrome
        content = self._content_height()
        return (chrome + self.HEADER_H + min(content, max(56, stage_room))
                + conf + self.INPUT_H)

    def _fit(self) -> None:
        """Ask the top-level window to match the content height."""
        win = self.window()
        if win is not None and win is not self:
            h = self.desired_height()
            win.setFixedHeight(h)

    # ── column helpers ────────────────────────────────────
    def _insert(self, widget: QWidget) -> None:
        self._stage.insertWidget(self._stage.count() - 1, widget)
        self.conversation.scroll_to_bottom()
        QTimer.singleShot(0, self._fit)

    # ── controller contract ───────────────────────────────
    def add_user_message(self, text: str) -> None:
        self._drop_resting()
        self._insert(_Turn(text, "you"))
        self._ledger = None

    def begin_mike_stream(self):
        self._drop_resting()
        self._stream = _Turn("", "mike")
        self._insert(self._stream)
        return self._stream

    def add_mike_message(self, text: str) -> None:
        self._drop_resting()
        self._insert(_Turn(text, "mike"))

    def add_action_card(self, text: str):
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
        self._thinking = _Turn("Thinking…", "mike")
        self._thinking.setStyleSheet(f"color:{style.INK_MUTE};")
        self._insert(self._thinking)

    def hide_thinking(self) -> None:
        if self._thinking is not None:
            self._thinking.hide()
            self._stage.removeWidget(self._thinking)
            self._thinking.deleteLater()
            self._thinking = None

    def set_state(self, state: str) -> None:
        self._state = state
        self.mark.set_state(state)
        self.input.voice.set_state(state)
        self._state_lbl.setText(STATE_WORD.get(state, "").upper())
        self._stop.setVisible(state in ("thinking", "working", "responding", "speaking"))
        self.input.set_listening(state == "listening")

    def state(self) -> str:
        return self._state

    def window(self):  # noqa: A003
        return super().window()

    # overlays (settings / memory / personalisation) — secondary, summoned
    def _toggle_settings(self) -> None:
        if self.showing_overlay():
            self.close_overlays()
        else:
            self._open_settings()

    def _open_settings(self) -> None:
        self._overlay_open = True
        self._settings_view.reload()
        self._scroll.hide()
        self.confirm.hide()
        self._settings_view.show()
        win = self.window()
        if win is not None and win is not self:
            win.setFixedHeight(self.CAP_HEIGHT)

    def showing_overlay(self) -> bool:
        return getattr(self, "_overlay_open", False)

    def close_overlays(self) -> None:
        self._overlay_open = False
        self._settings_view.hide()
        self._scroll.show()
        QTimer.singleShot(0, self._fit)

    def clear(self) -> None:
        while self._stage.count() > 1:
            item = self._stage.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._resting = None
        self._stream = None
        self._ledger = None
        self._show_resting()
        self.set_state("idle")

    # ── the floating, warm-dark material ──────────────────
    def paintEvent(self, _e) -> None:
        from PySide6.QtGui import QLinearGradient, QPen

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        m = self.SHADOW
        radius = 18.0
        bx, by = m, m - 6
        bw, bh = self.width() - 2 * m, self.height() - (m - 6) - m

        # soft drop shadow — several expanding rounded rects, fading out and
        # offset downward, an inexpensive blur that makes the panel float.
        for i in range(m, 0, -2):
            a = int(4 + 40 * (1 - i / m) ** 2.2)
            sh = QPainterPath()
            sh.addRoundedRect(bx - i, by - i + 5, bw + 2 * i, bh + 2 * i,
                              radius + i, radius + i)
            p.fillPath(sh, QColor(0, 0, 0, a))

        body = QPainterPath()
        body.addRoundedRect(bx, by, bw, bh, radius, radius)

        # lit from above: a barely-there vertical gradient, top a touch lighter
        grad = QLinearGradient(0, by, 0, by + bh)
        top = QColor(style.GROUND_RAISED)
        grad.setColorAt(0.0, top)
        grad.setColorAt(0.16, QColor(style.GROUND))
        grad.setColorAt(1.0, QColor(style.GROUND_SUNK))
        p.fillPath(body, grad)

        # a 1px highlight along the very top edge — the lit rim
        p.setClipPath(body)
        hi = QPen(QColor(255, 255, 255, 16)); hi.setWidthF(1.2)
        p.setPen(hi); p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(bx + 0.6, by + 0.6, bw - 1.2, bh - 1.2, radius, radius)
        p.setClipping(False)

        # the outer hairline, keeping the edge crisp against any desktop
        border = QPen(QColor(style.HAIRLINE)); border.setWidthF(1.0)
        p.setPen(border); p.setBrush(Qt.NoBrush)
        p.drawPath(body)


def _build_stylesheet() -> str:
    return f"""
QScrollArea#stage, QScrollArea#settings {{ background: transparent; border: none; }}
QPushButton#menu {{
    background: transparent; color: {style.INK_MUTE};
    border: none; font-size: 16px; padding: 0 2px;
}}
QPushButton#menu:hover {{ color: {style.INK}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{
    background: {style.INK_FAINT}; border-radius: 4px; min-height: 28px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QFrame#inputBar {{
    background: {style.GROUND_RAISED};
    border: 1px solid {style.HAIRLINE};
    border-radius: 12px;
}}
QFrame#ledger {{
    background: {style.GROUND_SUNK};
    border: 1px solid {style.HAIRLINE};
    border-radius: 10px;
}}
QFrame#confirm {{
    background: {style.GROUND_RAISED};
    border: 1px solid {style.WARN};
    border-radius: 12px;
}}
QPushButton#stop {{
    background: transparent; color: {style.INK_MUTE};
    border: 1px solid {style.HAIRLINE}; border-radius: 8px;
    padding: 4px 12px; font-size: 11px;
}}
QPushButton#stop:hover {{ color: {style.STOP}; border-color: {style.STOP}; }}
QPushButton#allow {{
    background: {style.accent()}; color: #17140F;
    border: none; border-radius: 8px; padding: 7px 18px;
    font-size: 13px; font-weight: 600;
}}
QPushButton#deny {{
    background: transparent; color: {style.INK_SOFT};
    border: 1px solid {style.HAIRLINE}; border-radius: 8px;
    padding: 7px 16px; font-size: 13px;
}}
QPushButton#deny:hover {{ color: {style.INK}; border-color: {style.INK_MUTE}; }}
"""
