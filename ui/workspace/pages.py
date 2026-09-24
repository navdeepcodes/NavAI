"""Settings — everything about Mike that isn't the conversation.

One surface, reached from the foot of the rail, with a tab for each concern:
General (you, and how Mike looks), Voice, Memory, Activity (what Mike has done
on this computer), Privacy, and About. Each is a real surface over real state,
not a screen invented to fill a menu: Memory reads and edits the memory store,
Activity is the actual record of Mike's actions, Voice drives the live
engines, and every switch is read by the thing it claims to control.

Built from one small set of primitives — a group heading, a card, a setting
row with its control on the right, a painted switch — so every tab reads as
part of the same product.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mike_panel import _Swatch, _hotkey_hint, _this_machine
from ui.workspace.icons import draw

#: The reading column every settings tab is laid out in.
COLUMN = 720


# ══ primitives ═════════════════════════════════════════════

class Switch(QWidget):
    """A clean painted toggle."""
    toggled = Signal(bool)

    def __init__(self, on: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._on = on
        self.setFixedSize(40, 24)
        self.setCursor(Qt.PointingHandCursor)

    def set_on(self, on: bool) -> None:
        if on != self._on:
            self._on = on
            self.update()

    def is_on(self) -> bool:
        return self._on

    def mousePressEvent(self, _e) -> None:
        self._on = not self._on
        self.update()
        self.toggled.emit(self._on)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        track = QColor(style.accent()) if self._on else QColor(style.INK_FAINT)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        p.setBrush(QColor("#FFFFFF"))
        d = h - 6
        x = (w - d - 3) if self._on else 3
        p.drawEllipse(QRectF(x, 3, d, d))


def _label(text: str, px: int = style.BODY, colour: str | None = None,
           weight: QFont.Weight = QFont.Weight.Normal, wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(wrap)
    lbl.setFont(style.font(px, weight))
    lbl.setStyleSheet(f"color:{colour or style.INK};background:transparent;")
    return lbl


def _group(title: str) -> QLabel:
    """The heading above a card: what this group of settings is about."""
    lbl = _label(title, style.SMALL, style.INK_SOFT, QFont.Weight.DemiBold)
    lbl.setContentsMargins(4, 10, 0, 2)
    return lbl


def _card() -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    col = QVBoxLayout(card)
    col.setContentsMargins(20, 6, 20, 6)
    col.setSpacing(0)
    return card, col


def _rule() -> QFrame:
    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background:{style.HAIRLINE};border:none;")
    return sep


def _row(title: str, desc: str = "", control: QWidget | None = None) -> QWidget:
    """A setting: what it is on the left, its control on the right."""
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 14, 0, 14)
    row.setSpacing(18)
    text = QVBoxLayout()
    text.setSpacing(3)
    text.addWidget(_label(title, style.BODY, style.INK, QFont.Weight.Medium))
    if desc:
        text.addWidget(_label(desc, style.SMALL, style.INK_MUTE))
    row.addLayout(text, 1)
    if control is not None:
        row.addWidget(control, 0, Qt.AlignVCenter)
    return w


def _rows_card(rows: list[QWidget]) -> QFrame:
    card, col = _card()
    for i, r in enumerate(rows):
        if i:
            col.addWidget(_rule())
        col.addWidget(r)
    return card


def _rel_time(ts: float) -> str:
    try:
        delta = datetime.now().timestamp() - float(ts)
    except Exception:
        return ""
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 7 * 86400:
        return f"{int(delta // 86400)}d ago"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%d %b")
    except Exception:
        return ""


def _arm(button: QPushButton, confirm_text: str, action, idle_text: str | None = None) -> None:
    """Make a destructive button ask once before acting.

    First click turns it into a red "Delete?"-style confirm; a second click
    within three seconds acts, otherwise it quietly reverts. One stray click
    must never permanently erase something that matters.
    """
    idle = idle_text if idle_text is not None else button.text()
    idle_name = button.objectName()
    min_w, max_w = button.minimumWidth(), button.maximumWidth()
    state = {"armed": False}
    timer = QTimer(button)
    timer.setSingleShot(True)

    def revert():
        state["armed"] = False
        button.setText(idle)
        button.setObjectName(idle_name)
        button.setMinimumWidth(min_w)
        button.setMaximumWidth(max_w)
        button.style().unpolish(button); button.style().polish(button)

    def clicked():
        if state["armed"]:
            timer.stop()
            revert()
            action()
            return
        state["armed"] = True
        button.setText(confirm_text)
        button.setObjectName("danger")
        button.setMaximumWidth(16777215)
        button.setMinimumWidth(button.fontMetrics().horizontalAdvance(confirm_text) + 28)
        button.style().unpolish(button); button.style().polish(button)
        timer.start(3000)

    timer.timeout.connect(revert)
    button.clicked.connect(clicked)


def _button(text: str, name: str = "ghost") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(name)
    b.setCursor(Qt.PointingHandCursor)
    b.setFont(style.font(style.SMALL, QFont.Weight.Medium))
    return b


def settings_qss() -> str:
    return f"""
QWidget#settings {{ background: transparent; }}
QScrollArea#tabBody {{ background: transparent; border: none; }}
QFrame#card {{
    background: {style.GROUND_RAISED};
    border: 1px solid {style.HAIRLINE};
    border-radius: 14px;
}}
QLineEdit#field, QPlainTextEdit#field {{
    background: {style.GROUND};
    border: 1px solid {style.HAIRLINE};
    border-radius: 10px;
    padding: 8px 12px;
    color: {style.INK};
    selection-background-color: {style.accent()};
}}
QLineEdit#field:focus, QPlainTextEdit#field:focus {{
    border: 1px solid {style.accent()};
}}
QPushButton#pill {{
    background: {style.accent()}; color: #17140F;
    border: none; border-radius: 9px; padding: 8px 18px;
}}
QPushButton#pill:hover {{ background: {QColor(style.accent()).lighter(106).name()}; }}
QPushButton#ghost {{
    background: transparent; color: {style.INK_SOFT};
    border: 1px solid {style.HAIRLINE}; border-radius: 9px;
    padding: 7px 14px;
}}
QPushButton#ghost:hover {{ color: {style.INK}; border-color: {style.INK_MUTE}; }}
QPushButton#danger {{
    background: {style.STOP}; color: #FFFFFF; border: none;
    border-radius: 9px; padding: 7px 14px; font-weight: 600;
}}
QPushButton#seg {{
    background: transparent; color: {style.INK_SOFT};
    border: 1px solid {style.HAIRLINE}; border-radius: 9px;
    padding: 6px 14px;
}}
QPushButton#seg:hover {{ color: {style.INK}; }}
QPushButton#seg:checked {{
    background: {style.INK}; color: {style.GROUND}; border: 1px solid {style.INK};
}}
QPushButton#iconx {{
    background: transparent; color: {style.INK_MUTE};
    border: none; border-radius: 8px; padding: 0 8px;
}}
QPushButton#iconx:hover {{ color: {style.STOP}; background: {style.GROUND_SUNK}; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 6px 3px; }}
QScrollBar::handle:vertical {{ background: {style.INK_FAINT}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


def _centred(widget: QWidget, max_width: int = COLUMN, margins=(40, 0, 40, 0)) -> QWidget:
    """Put `widget` in a column no wider than max_width, centred in the space."""
    outer = QWidget()
    row = QHBoxLayout(outer)
    row.setContentsMargins(*margins)
    row.setSpacing(0)
    row.addStretch(1)
    widget.setMaximumWidth(max_width)
    row.addWidget(widget, 100)
    row.addStretch(1)
    return outer


class _Tab(QScrollArea):
    """One settings tab: a scrolling, centred column of groups and cards."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("tabBody")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        column = QWidget()
        self.body = QVBoxLayout(column)
        self.body.setContentsMargins(0, 18, 0, 40)
        self.body.setSpacing(8)
        self.setWidget(_centred(column))
        self.build()

    def build(self) -> None:  # overridden
        pass

    def add(self, w: QWidget) -> None:
        self.body.addWidget(w)

    def reload(self) -> None:
        """Rebuild from live state (memory, activity)."""
        while self.body.count():
            item = self.body.takeAt(0)
            w = item.widget()
            if w is not None:
                # Hidden as well as deleted: a detached widget stays painted at
                # its old position until the deferred delete runs.
                w.hide()
                w.deleteLater()
        self.build()


# ══ General: you, and how Mike looks ═══════════════════════

class GeneralTab(_Tab):

    def __init__(self, hooks: dict, on_restyle, parent=None) -> None:
        self._hooks = hooks
        self._on_restyle = on_restyle
        super().__init__(parent)

    def build(self) -> None:
        from config import preferences

        self.add(_group("You"))
        card, col = _card()
        col.setContentsMargins(20, 18, 20, 18)
        col.setSpacing(8)
        col.addWidget(_label("What should Mike call you?", style.SMALL, style.INK_SOFT,
                             QFont.Weight.Medium))
        self._name = QLineEdit(str(preferences.get("profile_name", "") or ""))
        self._name.setObjectName("field")
        self._name.setFont(style.font(style.BODY))
        self._name.setPlaceholderText("Your name")
        col.addWidget(self._name)
        col.addSpacing(8)
        col.addWidget(_label("Anything that helps Mike help you", style.SMALL,
                             style.INK_SOFT, QFont.Weight.Medium))
        self._about = QPlainTextEdit(str(preferences.get("profile_about", "") or ""))
        self._about.setObjectName("field")
        self._about.setFont(style.font(style.BODY))
        self._about.setFixedHeight(92)
        self._about.setPlaceholderText(
            "What you're studying or working on, how you like things explained…")
        col.addWidget(self._about)
        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 6, 0, 0)
        hint = _label(f"Stays on {_this_machine()} — nothing is sent anywhere.",
                      style.CAPTION, style.INK_MUTE)
        save_row.addWidget(hint, 1)
        self._saved = _label("", style.SMALL, style.GOOD, wrap=False)
        save_row.addWidget(self._saved, 0, Qt.AlignVCenter)
        save = _button("Save", "pill")
        save.clicked.connect(self._save)
        save_row.addWidget(save, 0, Qt.AlignVCenter)
        col.addLayout(save_row)
        self.add(card)

        self.add(_group("Appearance"))
        theme = QWidget()
        trow = QHBoxLayout(theme)
        trow.setContentsMargins(0, 0, 0, 0)
        trow.setSpacing(6)
        self._theme_btns: dict[str, QPushButton] = {}
        current = str(preferences.get("theme", "system") or "system")
        for key, label in (("system", "System"), ("light", "Light"), ("dark", "Dark")):
            b = _button(label, "seg")
            b.setCheckable(True)
            b.setChecked(key == current)
            b.clicked.connect(lambda _=False, k=key: self._set_theme(k))
            self._theme_btns[key] = b
            trow.addWidget(b)

        swatches = QWidget()
        arow = QHBoxLayout(swatches)
        arow.setContentsMargins(0, 0, 0, 0)
        arow.setSpacing(6)
        self._swatches: list[_Swatch] = []
        cur_accent = str(preferences.get("accent", "") or "amber").lower()
        for name, colour in style.accent_presets().items():
            sw = _Swatch(name, colour, self._set_accent)
            sw.set_selected(name == cur_accent)
            self._swatches.append(sw)
            arow.addWidget(sw)

        motion = Switch(bool(preferences.get("reduced_motion", False)))
        motion.toggled.connect(self._set_motion)

        self.add(_rows_card([
            _row("Theme", "Light, dark, or follow your system.", theme),
            _row("Accent", "Mike's colour, used sparingly.", swatches),
            _row("Reduce motion", "Calmer, simpler animations everywhere in Mike.", motion),
        ]))
        self.body.addStretch(1)

    def _save(self) -> None:
        from config import preferences
        preferences.set_value("profile_name", self._name.text().strip())
        preferences.set_value("profile_about", self._about.toPlainText().strip())
        self._saved.setText("Saved")
        QTimer.singleShot(2200, lambda: self._saved.setText(""))
        hook = self._hooks.get("profile_changed")
        if hook:
            hook()

    def _set_theme(self, key: str) -> None:
        from config import preferences
        preferences.set_value("theme", key)
        for k, b in self._theme_btns.items():
            b.setChecked(k == key)
        style.apply_theme()
        self._on_restyle()

    def _set_accent(self, name: str) -> None:
        from config import preferences
        preferences.set_value("accent", name)
        for sw in self._swatches:
            sw.set_selected(sw._name == name)
        self._on_restyle()

    def _set_motion(self, on: bool) -> None:
        from config import preferences
        preferences.set_value("reduced_motion", on)


# ══ Voice ══════════════════════════════════════════════════

class _VoiceRow(QWidget):
    """A selectable voice in the picker."""
    picked = Signal(str)

    def __init__(self, key: str, label: str, selected: bool, parent=None) -> None:
        super().__init__(parent)
        self._key = key
        self._selected = selected
        self._label = label
        self._hover = False
        self.setFixedHeight(46)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(label)

    def set_selected(self, on: bool) -> None:
        self._selected = on
        self.update()

    def enterEvent(self, _e):
        self._hover = True
        self.update()

    def leaveEvent(self, _e):
        self._hover = False
        self.update()

    def mousePressEvent(self, _e) -> None:
        self.picked.emit(self._key)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        h = self.height()
        cy = h / 2
        ring = QColor(style.accent() if self._selected else style.INK_MUTE)
        pen = p.pen()
        pen.setColor(ring)
        pen.setWidthF(1.6)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(1, cy - 8, 16, 16))
        if self._selected:
            p.setPen(Qt.NoPen)
            p.setBrush(ring)
            p.drawEllipse(QRectF(5, cy - 4, 8, 8))
        name, _, desc = self._label.partition(" — ")
        p.setPen(QColor(style.INK))
        p.setFont(style.font(style.BODY, QFont.Weight.Medium))
        fm = p.fontMetrics()
        p.drawText(QRectF(30, 0, 200, h), Qt.AlignVCenter | Qt.AlignLeft, name)
        if desc:
            p.setPen(QColor(style.INK_MUTE))
            p.setFont(style.font(style.SMALL))
            p.drawText(QRectF(30 + fm.horizontalAdvance(name) + 10, 0, 400, h),
                       Qt.AlignVCenter | Qt.AlignLeft, desc)


class VoiceTab(_Tab):

    def __init__(self, hooks: dict, parent=None) -> None:
        self._hooks = hooks
        self._rows: list[_VoiceRow] = []
        super().__init__(parent)

    def build(self) -> None:
        from config import preferences

        self.add(_group("Speaking"))
        card, col = _card()
        col.setContentsMargins(20, 16, 20, 16)
        col.setSpacing(4)
        col.addWidget(_label("Mike's voice", style.SMALL, style.INK_SOFT, QFont.Weight.Medium))
        self._status_line = _label(self._voice_line(), style.READ, style.INK, QFont.Weight.Medium)
        col.addWidget(self._status_line)
        col.addWidget(_label(
            f"Generated on {_this_machine()} — fast to start, light on resources, "
            "and never sent anywhere.", style.SMALL, style.INK_MUTE))
        picker = self._voice_picker()
        if picker:
            col.addSpacing(8)
            col.addWidget(_rule())
            col.addSpacing(4)
            for w in picker:
                col.addWidget(w)
        self.add(card)

        speak = Switch(bool(preferences.get("voice_enabled", True)))
        speak.toggled.connect(lambda on: self._flip("voice_enabled", on, "on_voice_toggle"))
        self.add(_rows_card([
            _row("Speak answers aloud",
                 "Mike reads his replies out. Turn off for a silent, text-only Mike.",
                 speak),
        ]))

        self.add(_group("Listening"))
        wake = Switch(bool(preferences.get("wake_word_enabled", True)))
        wake.toggled.connect(lambda on: self._flip("wake_word_enabled", on, "on_wake_toggle"))
        self.add(_rows_card([
            _row("“Hey Mike”", "Say it from anywhere to start talking, hands-free.", wake),
            _row("Talk with a click", "Click the mic in the message box, or press F6. "
                 "Mike stops listening when you pause.", _key_hint("F6")),
            _row("Interrupt", "Start talking, click the mic, or press Esc — "
                 "Mike stops speaking straight away.", _key_hint("Esc")),
        ]))
        self.body.addStretch(1)

    def _flip(self, key: str, on: bool, hook: str) -> None:
        from config import preferences
        preferences.set_value(key, on)
        h = self._hooks.get(hook)
        if h:
            h(on)

    def _voice_picker(self) -> list[QWidget]:
        try:
            from voice.providers.piper import PiperVoice, VOICES, _piper_home
            ok, _ = PiperVoice().available()
            if not ok:
                return []
            home = _piper_home()
        except Exception:
            return []
        # Only offer voices whose model is actually bundled on this machine.
        present = {
            k: v for k, v in VOICES.items()
            if home is not None and (home / "voices" / f"{k}.onnx").exists()
        }
        if len(present) < 2:
            return []
        from config import preferences
        current = str(preferences.get("voice_piper_voice", "en_US-amy-medium"))
        rows: list[QWidget] = []
        for key, label in present.items():
            row = _VoiceRow(key, label, key == current)
            row.picked.connect(self._pick_voice)
            self._rows.append(row)
            rows.append(row)
        return rows

    def _pick_voice(self, key: str) -> None:
        from config import preferences
        preferences.set_value("voice_piper_voice", key)
        preferences.set_value("voice_provider", "piper")
        for r in self._rows:
            r.set_selected(r._key == key)
        self._status_line.setText(self._voice_line())
        # apply live, so the next thing Mike says uses the new voice
        h = self._hooks.get("on_voice_changed")
        if h:
            h()

    def _voice_line(self) -> str:
        try:
            from config import preferences
            p = str(preferences.get("voice_provider", "piper")).lower()
            if p == "piper":
                from voice.providers.piper import PiperVoice, VOICES
                if PiperVoice().available()[0]:
                    v = str(preferences.get("voice_piper_voice", "en_US-amy-medium"))
                    return VOICES.get(v, v).split(" — ")[0] + " · neural voice"
            if p == "qwen":
                return f"{preferences.get('voice_qwen_speaker', 'Ryan')} · neural voice"
        except Exception:
            pass
        try:
            from voice.providers import native_provider_class
            ok, why = native_provider_class()().available()
            if ok:
                return why
        except Exception:
            pass
        return "The built-in system voice"


def _key_hint(text: str) -> QLabel:
    """A keyboard key, drawn as a small keycap."""
    lbl = QLabel(text)
    lbl.setFont(style.font(style.CAPTION, QFont.Weight.DemiBold))
    lbl.setStyleSheet(
        f"color:{style.INK_SOFT};background:{style.GROUND};"
        f"border:1px solid {style.HAIRLINE};border-bottom-width:2px;"
        f"border-radius:6px;padding:3px 8px;")
    return lbl


# ══ Memory ═════════════════════════════════════════════════

class MemoryTab(_Tab):

    def build(self) -> None:
        try:
            from brain import memory_store
            rows = memory_store.all_memories(limit=300)
        except Exception:
            rows = []

        top = QWidget()
        trow = QHBoxLayout(top)
        trow.setContentsMargins(4, 4, 0, 6)
        trow.addWidget(_label(
            f"What Mike remembers about you, kept on {_this_machine()}. "
            "Forget anything you like.", style.BODY, style.INK_SOFT), 1)
        if rows:
            forget = _button("Forget all")
            _arm(forget, "Forget everything?", self._forget_all)
            trow.addWidget(forget, 0, Qt.AlignVCenter)
        self.add(top)

        if not rows:
            self.add(_empty_card(
                "memory", "Nothing kept yet",
                "Tell Mike something worth keeping — “remember that my exams "
                "start on the 12th” — and it will appear here."))
            self.body.addStretch(1)
            return

        card, col = _card()
        for i, r in enumerate(rows):
            if i:
                col.addWidget(_rule())
            col.addWidget(self._memory_row(r))
        self.add(card)
        self.body.addStretch(1)

    def _memory_row(self, r: dict) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 12, 0, 12)
        row.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(3)
        text.addWidget(_label(str(r.get("content", "")), style.BODY, style.INK))
        meta = str(r.get("category", "") or "").capitalize()
        when = _rel_time(r.get("updated_at") or r.get("created_at") or 0)
        text.addWidget(_label(" · ".join(x for x in (meta, when) if x),
                              style.CAPTION, style.INK_MUTE))
        row.addLayout(text, 1)
        x = _button("Forget", "iconx")
        _arm(x, "Forget?", lambda mid=r.get("id"): self._forget_one(mid))
        row.addWidget(x, 0, Qt.AlignVCenter)
        return w

    def _forget_one(self, mid) -> None:
        try:
            from brain import memory_store
            memory_store.forget(memory_id=mid)
        except Exception:
            pass
        self.reload()

    def _forget_all(self) -> None:
        try:
            from brain import memory_store
            memory_store.forget(query="everything")
        except Exception:
            pass
        self.reload()


# ══ Activity: what Mike has done ═══════════════════════════

class ActivityTab(_Tab):

    def build(self) -> None:
        try:
            from brain import activity_store
            rows = activity_store.recent(limit=100)
        except Exception:
            rows = []
        self.add(_label(
            f"Everything Mike has done on {_this_machine()} — files he wrote, apps "
            "he opened, commands he ran — newest first.", style.BODY, style.INK_SOFT))
        if not rows:
            self.add(_empty_card(
                "activity", "Nothing yet",
                "When Mike opens, writes or changes something for you, it's "
                "recorded here, so you can always see what he did."))
            self.body.addStretch(1)
            return
        card, col = _card()
        for i, r in enumerate(rows):
            if i:
                col.addWidget(_rule())
            col.addWidget(self._action_row(r))
        self.add(card)
        self.body.addStretch(1)

    def _action_row(self, r: dict) -> QWidget:
        ok = bool(r.get("succeeded", 1))
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 11, 0, 11)
        row.setSpacing(12)
        row.addWidget(_StatusDot(ok), 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(_label(str(r.get("action", "")), style.BODY, style.INK))
        outcome = str(r.get("outcome") or "").strip()
        if not ok and outcome:
            text.addWidget(_label(outcome[:160], style.CAPTION, style.STOP))
        row.addLayout(text, 1)
        row.addWidget(_label(_rel_time(r.get("started_at", 0)), style.CAPTION,
                             style.INK_MUTE, wrap=False), 0, Qt.AlignTop)
        return w


class _StatusDot(QWidget):
    def __init__(self, ok: bool, parent=None) -> None:
        super().__init__(parent)
        self._ok = ok
        self.setFixedSize(20, 20)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(style.GOOD if self._ok else style.STOP)
        tile = QColor(col)
        tile.setAlpha(40)
        p.setPen(Qt.NoPen)
        p.setBrush(tile)
        p.drawEllipse(QRectF(0, 0, 20, 20))
        draw(p, "check" if self._ok else "close", QRectF(3, 3, 14, 14), col, 1.8)


def _empty_card(icon: str, title: str, body: str) -> QWidget:
    card, col = _card()
    col.setContentsMargins(24, 28, 24, 28)
    col.setSpacing(6)
    ic = _IconTile(icon)
    col.addWidget(ic, 0, Qt.AlignHCenter)
    col.addSpacing(6)
    t = _label(title, style.BODY, style.INK, QFont.Weight.DemiBold)
    t.setAlignment(Qt.AlignHCenter)
    col.addWidget(t)
    b = _label(body, style.SMALL, style.INK_MUTE)
    b.setAlignment(Qt.AlignHCenter)
    col.addWidget(b)
    return card


class _IconTile(QWidget):
    def __init__(self, icon: str, size: int = 40, parent=None) -> None:
        super().__init__(parent)
        self._icon = icon
        self.setFixedSize(size, size)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        s = self.width()
        tile = QColor(style.accent())
        tile.setAlpha(34)
        p.setPen(Qt.NoPen)
        p.setBrush(tile)
        p.drawRoundedRect(QRectF(0, 0, s, s), 11, 11)
        draw(p, self._icon, QRectF(s * 0.25, s * 0.25, s * 0.5, s * 0.5),
             QColor(style.accent()).darker(125) if not style.is_dark() else QColor(style.accent()),
             1.8)


# ══ Privacy ════════════════════════════════════════════════

class PrivacyTab(_Tab):

    def build(self) -> None:
        self.add(_group("Stays on this machine"))
        card, col = _card()
        col.setContentsMargins(20, 16, 20, 16)
        col.addWidget(_label(
            f"Everything Mike does happens on {_this_machine()}. The model runs "
            "locally, your files are read locally, and nothing — not your "
            "messages, not your screen, not your memory — is sent to a server. "
            "There is no account and no telemetry.", style.BODY, style.INK))
        self.add(card)

        self.add(_group("Before Mike changes anything"))
        card2, col2 = _card()
        col2.setContentsMargins(20, 16, 20, 16)
        col2.addWidget(_label(
            "Mike asks first before anything he can't quietly undo — deleting "
            "or overwriting a file, sending a message, running something that "
            "changes your system. You approve each one, in the moment, and you "
            "can stop him at any time with Stop or Esc.", style.BODY, style.INK_SOFT))
        self.add(card2)

        self.add(_group("Where your data lives"))
        rows: list[QWidget] = []
        try:
            from config import preferences
            from brain import memory_store
            for title, path in (("Chats, memory and activity", memory_store.db_path()),
                                ("Preferences", preferences.path())):
                w = QWidget()
                c = QVBoxLayout(w)
                c.setContentsMargins(0, 12, 0, 12)
                c.setSpacing(3)
                c.addWidget(_label(title, style.BODY, style.INK, QFont.Weight.Medium))
                p = _label(path, style.CAPTION, style.INK_MUTE)
                p.setTextInteractionFlags(Qt.TextSelectableByMouse)
                c.addWidget(p)
                rows.append(w)
        except Exception:
            pass
        if rows:
            self.add(_rows_card(rows))
        self.body.addStretch(1)


# ══ About ══════════════════════════════════════════════════

class AboutTab(_Tab):

    def build(self) -> None:
        from ui.panel.mark import PresenceMark
        try:
            from config.settings import VERSION
        except Exception:
            VERSION = ""

        card, col = _card()
        col.setContentsMargins(22, 22, 22, 22)
        head = QHBoxLayout()
        head.setSpacing(14)
        mark = PresenceMark(40)
        head.addWidget(mark, 0, Qt.AlignVCenter)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(_label("Mike", style.TITLE, style.INK, QFont.Weight.DemiBold))
        import platform
        plat = {"Windows": "Windows", "Darwin": "macOS"}.get(platform.system(), platform.system())
        names.addWidget(_label(f"Version {VERSION} · {plat}", style.SMALL, style.INK_MUTE))
        head.addLayout(names, 1)
        col.addLayout(head)
        col.addSpacing(12)
        col.addWidget(_label(
            "A personal assistant that lives on your computer and can actually "
            "use it — open apps, find and write files, read your screen, fix "
            "code, and remember what matters.", style.BODY, style.INK_SOFT))
        self.add(card)

        self.add(_group("How Mike thinks"))
        try:
            from config.ollama import OLLAMA_CHAT_MODEL, OLLAMA_VISION_MODEL
        except Exception:
            OLLAMA_CHAT_MODEL, OLLAMA_VISION_MODEL = "a local model", "a local model"
        self.add(_rows_card([
            _row("Language model", f"{OLLAMA_CHAT_MODEL} · runs through Ollama, on-device",
                 None),
            _row("Vision", f"{OLLAMA_VISION_MODEL} · for images and your screen", None),
        ]))

        self.add(_group("Keyboard"))
        self.add(_rows_card([
            _row("Bring Mike to you, from any app", "", _key_hint(_hotkey_hint())),
            _row("New chat", "", _key_hint("Ctrl+N")),
            _row("Show or hide the sidebar", "", _key_hint("Ctrl+B")),
            _row("Talk to Mike", "", _key_hint("F6")),
            _row("Stop Mike", "", _key_hint("Esc")),
            _row("New line in a message", "", _key_hint("Shift+Enter")),
        ]))
        self.body.addStretch(1)


# ══ the settings surface ═══════════════════════════════════

class _TabBar(QWidget):
    """Text tabs with an accent underline on the one you're on."""

    selected = Signal(str)

    def __init__(self, tabs: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self._tabs = tabs
        self._current = tabs[0][0]
        self._hover: str | None = None
        self._rects: dict[str, QRectF] = {}
        self.setFixedHeight(42)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def set_current(self, key: str) -> None:
        self._current = key
        self.update()

    def _layout(self) -> None:
        f = style.font(style.BODY, QFont.Weight.Medium)
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(f)
        x = 4.0
        self._rects.clear()
        for key, label in self._tabs:
            w = fm.horizontalAdvance(label) + 20
            self._rects[key] = QRectF(x, 0, w, self.height())
            x += w + 6

    def mouseMoveEvent(self, e) -> None:
        self._layout()
        hit = next((k for k, r in self._rects.items() if r.contains(e.position())), None)
        if hit != self._hover:
            self._hover = hit
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = None
        self.update()

    def mousePressEvent(self, e) -> None:
        self._layout()
        for key, r in self._rects.items():
            if r.contains(e.position()):
                self.selected.emit(key)
                return

    def paintEvent(self, _e) -> None:
        self._layout()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        h = self.height()
        rule = QColor(style.HAIRLINE)
        p.fillRect(QRectF(0, h - 1, self.width(), 1), rule)
        for key, label in self._tabs:
            r = self._rects[key]
            on = key == self._current
            p.setFont(style.font(style.BODY, QFont.Weight.DemiBold if on else QFont.Weight.Medium))
            p.setPen(QColor(style.INK if on or key == self._hover else style.INK_MUTE))
            p.drawText(r.adjusted(0, 0, 0, -4), Qt.AlignCenter, label)
            if on:
                p.setPen(Qt.NoPen)
                p.setBrush(style.qaccent())
                p.drawRoundedRect(QRectF(r.x() + 8, h - 3, r.width() - 16, 3), 1.5, 1.5)


class SettingsPage(QWidget):
    """The one place for everything that isn't the conversation."""

    restyle_needed = Signal()
    closed = Signal()

    TABS = [
        ("general", "General"),
        ("voice", "Voice"),
        ("memory", "Memory"),
        ("activity", "Activity"),
        ("privacy", "Privacy"),
        ("about", "About"),
    ]

    def __init__(self, hooks: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("settings")
        self._hooks = hooks or {}
        self._tabs: dict[str, _Tab] = {}
        self._current = "general"

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        head = QWidget()
        hcol = QVBoxLayout(head)
        hcol.setContentsMargins(0, 8, 0, 0)
        hcol.setSpacing(10)
        top = QHBoxLayout()
        title = _label("Settings", style.DISPLAY, style.INK, QFont.Weight.DemiBold, wrap=False)
        top.addWidget(title, 1, Qt.AlignVCenter)
        done = _button("Done")
        done.setToolTip("Back to the chat (Esc)")
        done.clicked.connect(self.closed.emit)
        top.addWidget(done, 0, Qt.AlignVCenter)
        hcol.addLayout(top)
        self._bar = _TabBar(self.TABS)
        self._bar.selected.connect(self.open_tab)
        hcol.addWidget(self._bar)
        col.addWidget(_centred(head))

        self._stack = QStackedWidget()
        col.addWidget(self._stack, 1)

        self.setStyleSheet(settings_qss())
        self.open_tab("general")

    def _make(self, key: str) -> _Tab:
        if key == "general":
            return GeneralTab(self._hooks, self.restyle_needed.emit)
        if key == "voice":
            return VoiceTab(self._hooks)
        if key == "memory":
            return MemoryTab()
        if key == "activity":
            return ActivityTab()
        if key == "privacy":
            return PrivacyTab()
        return AboutTab()

    def open_tab(self, key: str) -> None:
        if key not in dict(self.TABS):
            key = "general"
        tab = self._tabs.get(key)
        if tab is None:
            tab = self._make(key)
            self._tabs[key] = tab
            self._stack.addWidget(tab)
        elif key in ("memory", "activity"):
            tab.reload()
        self._stack.setCurrentWidget(tab)
        self._bar.set_current(key)
        self._current = key

    def current_tab(self) -> str:
        return self._current

    def reload(self) -> None:
        """Entering Settings: what Mike remembers and did may have changed."""
        for key in ("memory", "activity"):
            if key in self._tabs:
                self._tabs[key].reload()
