"""The surfaces behind the sidebar — history, memory, profile, preferences,
voice, model, privacy, about.

Each is a real surface over real state, not a settings screen invented to fill
a rail: history reads the activity log, memory reads and edits the memory
store, profile and preferences edit what actually persists, voice drives the
live engines. Built from one small set of primitives (a page frame, cards,
rows, a painted switch) so the whole product reads as one considered thing.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mike_panel import _Swatch


# ══ primitives ═════════════════════════════════════════════

class Switch(QWidget):
    """A clean painted toggle."""
    toggled = Signal(bool)

    def __init__(self, on: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._on = on
        self.setFixedSize(42, 24)
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
        track = QColor(style.accent()) if self._on else QColor(style.HAIRLINE)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        knob = QColor("#FFFFFF") if self._on else QColor(style.INK_MUTE)
        p.setBrush(knob)
        d = h - 8
        x = (w - d - 4) if self._on else 4
        p.drawEllipse(QRectF(x, 4, d, d))


def _card() -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    col = QVBoxLayout(card)
    col.setContentsMargins(20, 16, 20, 16)
    col.setSpacing(4)
    return card, col


def _kicker(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setFont(style.label(10))
    lbl.setStyleSheet(
        f"color:{style.INK_FAINT};background:transparent;letter-spacing:1.6px;")
    return lbl


def _body(text: str, colour: str | None = None, size: int = 14) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setFont(style.voice(size))
    lbl.setStyleSheet(
        f"color:{colour or style.INK_SOFT};background:transparent;line-height:150%;")
    return lbl


class Page(QScrollArea):
    """A scrolling surface with a title and a centred body column."""

    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        board = QWidget()
        board.setStyleSheet("background:transparent;")
        row = QHBoxLayout(board)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)

        column = QWidget()
        column.setStyleSheet("background:transparent;")
        column.setMaximumWidth(680)
        self.body = QVBoxLayout(column)
        self.body.setContentsMargins(40, 40, 40, 40)
        self.body.setSpacing(14)

        head = QLabel(title)
        head.setFont(style.voice(26))
        head.setStyleSheet(
            f"color:{style.INK};background:transparent;font-weight:600;")
        self.body.addWidget(head)
        if subtitle:
            sub = _body(subtitle, style.INK_MUTE, 14)
            self.body.addWidget(sub)
        self.body.addSpacing(10)

        row.addWidget(column, 1)
        row.addStretch(1)
        self.setWidget(board)
        self.setStyleSheet(_PAGE_QSS())

    def add(self, w: QWidget) -> None:
        self.body.addWidget(w)

    def end(self) -> None:
        self.body.addStretch(1)


def _PAGE_QSS() -> str:
    return f"""
QScrollArea#page {{ background: transparent; border: none; }}
QFrame#card {{
    background: {style.GROUND_RAISED};
    border: 1px solid {style.HAIRLINE};
    border-radius: 14px;
}}
QLineEdit#field, QPlainTextEdit#field {{
    background: {style.GROUND_SUNK};
    border: 1px solid {style.HAIRLINE};
    border-radius: 10px;
    padding: 9px 12px;
    color: {style.INK};
    selection-background-color: {style.accent()};
}}
QLineEdit#field:focus, QPlainTextEdit#field:focus {{
    border: 1px solid {style.accent()};
}}
QPushButton#pill {{
    background: {style.accent()}; color: #17140F;
    border: none; border-radius: 9px; padding: 8px 18px;
    font-size: 13px; font-weight: 600;
}}
QPushButton#ghost {{
    background: transparent; color: {style.INK_SOFT};
    border: 1px solid {style.HAIRLINE}; border-radius: 9px;
    padding: 7px 16px; font-size: 13px;
}}
QPushButton#ghost:hover {{ color: {style.INK}; border-color: {style.INK_MUTE}; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 6px 3px; }}
QScrollBar::handle:vertical {{ background: {style.INK_FAINT}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


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
    return f"{int(delta // 86400)}d ago"


# ══ history ════════════════════════════════════════════════

class HistoryPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__("History",
                         "Everything Mike has done on this machine, newest first.",
                         parent)
        self.reload()

    def reload(self) -> None:
        # clear existing cards (keep the header + subtitle + spacing = 3 items)
        while self.body.count() > 3:
            item = self.body.takeAt(3)
            if item.widget():
                item.widget().deleteLater()

        try:
            from brain import activity_store
            rows = activity_store.recent(limit=80)
        except Exception:
            rows = []

        if not rows:
            self.add(_body("Nothing yet. When Mike opens something, writes a "
                           "file or runs a command, it shows up here.",
                           style.INK_MUTE))
            self.end()
            return

        top = QHBoxLayout()
        top.addStretch(1)
        clear = QPushButton("Clear history")
        clear.setObjectName("ghost")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self._clear)
        top.addWidget(clear)
        holder = QWidget(); holder.setStyleSheet("background:transparent;"); holder.setLayout(top)
        self.add(holder)

        card, col = _card()
        col.setSpacing(0)
        for i, r in enumerate(rows):
            if i:
                sep = QFrame(); sep.setFixedHeight(1)
                sep.setStyleSheet(f"background:{style.HAIRLINE};border:none;")
                col.addWidget(sep)
            col.addWidget(self._row(r))
        self.add(card)
        self.end()

    def _row(self, r: dict) -> QWidget:
        ok = bool(r.get("succeeded", 1))
        w = QWidget(); w.setStyleSheet("background:transparent;")
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 10, 0, 10)
        row.setSpacing(12)
        tick = QLabel("✓" if ok else "✕")
        tick.setStyleSheet(
            f"color:{style.GOOD if ok else style.STOP};background:transparent;font-size:13px;")
        row.addWidget(tick, 0, Qt.AlignTop)
        text = QLabel(str(r.get("action", "")))
        text.setWordWrap(True)
        text.setFont(style.voice(13))
        text.setStyleSheet(f"color:{style.INK};background:transparent;")
        row.addWidget(text, 1)
        when = QLabel(_rel_time(r.get("started_at", 0)))
        when.setFont(style.label(10, QFont.Weight.Normal))
        when.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
        row.addWidget(when, 0, Qt.AlignTop)
        return w

    def _clear(self) -> None:
        try:
            from brain import activity_store
            activity_store.clear()
        except Exception:
            pass
        self.reload()


# ══ memory ═════════════════════════════════════════════════

class MemoryPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__("Memory",
                         "What Mike remembers about you — kept on this machine, "
                         "yours to edit.", parent)
        self.reload()

    def reload(self) -> None:
        while self.body.count() > 3:
            item = self.body.takeAt(3)
            if item.widget():
                item.widget().deleteLater()
        try:
            from brain import memory_store
            rows = memory_store.all_memories(limit=300)
        except Exception:
            rows = []

        if not rows:
            self.add(_body("Nothing kept yet. Tell Mike something worth "
                           "remembering — “remember that I'm learning Python "
                           "this term” — and it'll appear here.", style.INK_MUTE))
            self.end()
            return

        top = QHBoxLayout()
        count = QLabel(f"{len(rows)} kept")
        count.setFont(style.label(11, QFont.Weight.Normal))
        count.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
        top.addWidget(count)
        top.addStretch(1)
        forget = QPushButton("Forget all")
        forget.setObjectName("ghost")
        forget.setCursor(Qt.PointingHandCursor)
        forget.clicked.connect(self._forget_all)
        top.addWidget(forget)
        holder = QWidget(); holder.setStyleSheet("background:transparent;"); holder.setLayout(top)
        self.add(holder)

        for r in rows:
            self.add(self._card(r))
        self.end()

    def _card(self, r: dict) -> QWidget:
        card, col = _card()
        row = QHBoxLayout()
        row.setSpacing(10)
        text = QLabel(str(r.get("content", "")))
        text.setWordWrap(True)
        text.setFont(style.voice(14))
        text.setStyleSheet(f"color:{style.INK};background:transparent;")
        row.addWidget(text, 1)
        x = QPushButton("✕")
        x.setObjectName("ghost")
        x.setCursor(Qt.PointingHandCursor)
        x.setFixedSize(28, 28)
        x.clicked.connect(lambda _=False, mid=r.get("id"): self._forget_one(mid))
        row.addWidget(x, 0, Qt.AlignTop)
        col.addLayout(row)
        meta = QLabel(str(r.get("category", "") or "").capitalize())
        meta.setFont(style.label(10, QFont.Weight.Normal))
        meta.setStyleSheet(f"color:{style.INK_FAINT};background:transparent;")
        col.addWidget(meta)
        return card

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


# ══ profile ════════════════════════════════════════════════

class ProfilePage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__("Profile",
                         "So Mike can talk to you like he knows you. Stays on "
                         "this machine — nothing is sent anywhere.", parent)
        from config import preferences
        card, col = _card()
        col.setSpacing(14)

        col.addWidget(_kicker("Your name"))
        self._name = QLineEdit(str(preferences.get("profile_name", "") or ""))
        self._name.setObjectName("field")
        self._name.setFont(style.voice(14))
        self._name.setPlaceholderText("What should Mike call you?")
        col.addWidget(self._name)

        col.addSpacing(4)
        col.addWidget(_kicker("About you"))
        self._about = QPlainTextEdit(str(preferences.get("profile_about", "") or ""))
        self._about.setObjectName("field")
        self._about.setFont(style.voice(14))
        self._about.setFixedHeight(96)
        self._about.setPlaceholderText(
            "What you're working on, what you're studying, how you like to "
            "work — anything that helps Mike be useful.")
        col.addWidget(self._about)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self._saved = QLabel("")
        self._saved.setFont(style.label(11, QFont.Weight.Normal))
        self._saved.setStyleSheet(f"color:{style.GOOD};background:transparent;")
        save_row.addWidget(self._saved, 0, Qt.AlignVCenter)
        save = QPushButton("Save")
        save.setObjectName("pill")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)
        save_row.addWidget(save)
        col.addLayout(save_row)

        self.add(card)
        self.end()

    def _save(self) -> None:
        from config import preferences
        preferences.set_value("profile_name", self._name.text().strip())
        preferences.set_value("profile_about", self._about.toPlainText().strip())
        self._saved.setText("Saved ✓")


# ══ preferences (appearance) ═══════════════════════════════

class PreferencesPage(Page):
    restyle_needed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Preferences",
                         "How Mike looks and feels on your machine.", parent)
        from config import preferences

        # ── theme ──
        card, col = _card()
        col.setSpacing(10)
        col.addWidget(_kicker("Appearance"))
        col.addWidget(_body("Light, dark, or follow your system.", style.INK_MUTE, 13))
        trow = QHBoxLayout()
        trow.setSpacing(8)
        self._theme_btns: dict[str, QPushButton] = {}
        current = str(preferences.get("theme", "system") or "system")
        for key, label in (("system", "System"), ("light", "Light"), ("dark", "Dark")):
            b = QPushButton(label)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(key == current)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._set_theme(k))
            self._theme_btns[key] = b
            trow.addWidget(b)
        trow.addStretch(1)
        holder = QWidget(); holder.setStyleSheet("background:transparent;"); holder.setLayout(trow)
        col.addWidget(holder)
        self.add(card)

        # ── accent ──
        card2, col2 = _card()
        col2.setSpacing(10)
        col2.addWidget(_kicker("Accent"))
        col2.addWidget(_body("Mike's colour, used sparingly across the app.",
                             style.INK_MUTE, 13))
        arow = QHBoxLayout(); arow.setSpacing(12)
        self._swatches: list[_Swatch] = []
        cur_accent = str(preferences.get("accent", "amber") or "amber").lower()
        for name, colour in style.accent_presets().items():
            sw = _Swatch(name, colour, self._set_accent)
            sw.set_selected(name == cur_accent or (cur_accent == "" and name == "amber"))
            self._swatches.append(sw)
            arow.addWidget(sw)
        arow.addStretch(1)
        holder2 = QWidget(); holder2.setStyleSheet("background:transparent;"); holder2.setLayout(arow)
        col2.addWidget(holder2)
        self.add(card2)

        # ── motion ──
        card3, col3 = _card()
        mrow = QHBoxLayout()
        mtext = QVBoxLayout(); mtext.setSpacing(2)
        mtext.addWidget(_kicker("Reduced motion"))
        mtext.addWidget(_body("Calmer animations, if motion bothers you.",
                              style.INK_MUTE, 13))
        mrow.addLayout(mtext, 1)
        self._motion = Switch(bool(preferences.get("reduced_motion", False)))
        self._motion.toggled.connect(
            lambda on: __import__("config").preferences.set_value("reduced_motion", on))
        mrow.addWidget(self._motion, 0, Qt.AlignVCenter)
        col3.addLayout(mrow)
        self.add(card3)
        self.end()

        self._restyle_seg()

    def _set_theme(self, key: str) -> None:
        from config import preferences
        preferences.set_value("theme", key)
        for k, b in self._theme_btns.items():
            b.setChecked(k == key)
        style.apply_theme()
        self.restyle_needed.emit()

    def _set_accent(self, name: str) -> None:
        from config import preferences
        preferences.set_value("accent", name)
        for sw in self._swatches:
            sw.set_selected(sw._name == name)
        self.restyle_needed.emit()

    def _restyle_seg(self) -> None:
        self.setStyleSheet(_PAGE_QSS() + f"""
QPushButton#seg {{
    background: {style.GROUND_SUNK}; color: {style.INK_SOFT};
    border: 1px solid {style.HAIRLINE}; border-radius: 9px;
    padding: 8px 18px; font-size: 13px;
}}
QPushButton#seg:checked {{
    background: {style.accent()}; color: #17140F; border: none; font-weight: 600;
}}
""")


# ══ voice ══════════════════════════════════════════════════

class _VoiceRow(QFrame):
    """A selectable voice in the picker."""
    picked = Signal(str)

    def __init__(self, key: str, label: str, selected: bool, parent=None) -> None:
        super().__init__(parent)
        self._key = key
        self._selected = selected
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background:transparent;")
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 8, 2, 8)
        row.setSpacing(12)
        self._dot = QLabel("◉" if selected else "○")
        self._dot.setStyleSheet(
            f"color:{style.accent() if selected else style.INK_MUTE};"
            f"background:transparent;font-size:15px;")
        row.addWidget(self._dot, 0, Qt.AlignVCenter)
        text = QLabel(label)
        text.setFont(style.voice(14))
        text.setStyleSheet(f"color:{style.INK};background:transparent;")
        row.addWidget(text, 1)

    def set_selected(self, on: bool) -> None:
        self._selected = on
        self._dot.setText("◉" if on else "○")
        self._dot.setStyleSheet(
            f"color:{style.accent() if on else style.INK_MUTE};"
            f"background:transparent;font-size:15px;")

    def mousePressEvent(self, _e) -> None:
        self.picked.emit(self._key)


class VoicePage(Page):
    def __init__(self, hooks: dict | None = None, parent=None) -> None:
        super().__init__("Voice",
                         "How Mike listens and speaks. Everything runs locally.",
                         parent)
        self._hooks = hooks or {}
        self._rows: list[_VoiceRow] = []
        from config import preferences

        # ── engine status ──
        card, col = _card()
        col.setSpacing(6)
        col.addWidget(_kicker("Speaking voice"))
        self._status_line = _body(self._voice_line(), style.INK, 15)
        col.addWidget(self._status_line)
        col.addWidget(_body(self._voice_detail(), style.INK_MUTE, 13))
        self.add(card)

        # ── voice picker ──
        picker = self._voice_picker()
        if picker is not None:
            self.add(picker)

        # ── speak toggle ──
        self.add(self._toggle_card(
            "Speak answers aloud",
            "Mike reads his replies out. Turn off for a silent, text-only Mike.",
            "voice_enabled", self._on_voice))

        # ── wake toggle ──
        self.add(self._toggle_card(
            "“Hey Mike” wake word",
            "Say “Hey Mike” from anywhere to start talking, hands-free.",
            "wake_word_enabled", self._on_wake))

        self.end()

    def _toggle_card(self, title, desc, pref_key, cb) -> QWidget:
        from config import preferences
        card, col = _card()
        row = QHBoxLayout()
        tcol = QVBoxLayout(); tcol.setSpacing(2)
        tcol.addWidget(_kicker(title))
        tcol.addWidget(_body(desc, style.INK_MUTE, 13))
        row.addLayout(tcol, 1)
        sw = Switch(bool(preferences.get(pref_key, True)))

        def _flip(on, key=pref_key, callback=cb):
            preferences.set_value(key, on)
            callback(on)
        sw.toggled.connect(_flip)
        row.addWidget(sw, 0, Qt.AlignVCenter)
        col.addLayout(row)
        return card

    def _on_voice(self, on: bool) -> None:
        h = self._hooks.get("on_voice_toggle")
        if h:
            h(on)

    def _on_wake(self, on: bool) -> None:
        h = self._hooks.get("on_wake_toggle")
        if h:
            h(on)

    def _voice_picker(self):
        try:
            from voice.providers.piper import PiperVoice, VOICES, _piper_home
            pv = PiperVoice()
            ok, _ = pv.available()
            if not ok:
                return None
            home = _piper_home()
        except Exception:
            return None
        # Only offer voices whose model is actually bundled on this machine.
        present = {
            k: v for k, v in VOICES.items()
            if home is not None and (home / "voices" / f"{k}.onnx").exists()
        }
        if len(present) < 2:
            return None
        from config import preferences
        current = str(preferences.get("voice_piper_voice", "en_US-amy-medium"))
        card, col = _card()
        col.setSpacing(2)
        col.addWidget(_kicker("Choose a voice"))
        col.addWidget(_body("Pick the one that sounds most like Mike to you.",
                            style.INK_MUTE, 13))
        col.addSpacing(4)
        for i, (key, label) in enumerate(present.items()):
            if i:
                sep = QFrame(); sep.setFixedHeight(1)
                sep.setStyleSheet(f"background:{style.HAIRLINE};border:none;")
                col.addWidget(sep)
            row = _VoiceRow(key, label, key == current)
            row.picked.connect(self._pick_voice)
            self._rows.append(row)
            col.addWidget(row)
        return card

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
                from voice.providers.piper import VOICES
                v = str(preferences.get("voice_piper_voice", "en_US-amy-medium"))
                label = VOICES.get(v, v)
                return f"{label} — neural, running on-device."
            if p == "qwen":
                return f"{preferences.get('voice_qwen_speaker', 'Ryan')} — neural, local."
        except Exception:
            pass
        try:
            from voice.providers import native_provider_class
            ok, why = native_provider_class()().available()
            if ok:
                return why
        except Exception:
            pass
        return "The built-in system voice."

    def _voice_detail(self) -> str:
        return ("Chosen for this machine: fast to start, light on resources, and "
                "it never leaves your PC.")


# ══ model ══════════════════════════════════════════════════

class ModelPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__("Model",
                         "The brain Mike thinks with — running entirely on your "
                         "machine.", parent)
        card, col = _card()
        col.setSpacing(6)
        col.addWidget(_kicker("Language model"))
        try:
            from config.ollama import OLLAMA_CHAT_MODEL
            model = OLLAMA_CHAT_MODEL
        except Exception:
            model = "a local model"
        col.addWidget(_body(model, style.INK, 17))
        col.addWidget(_body(
            "Runs through Ollama, on-device. Your conversations, files and "
            "screen never leave this PC — there is no cloud and no account.",
            style.INK_MUTE, 13))
        self.add(card)

        card2, col2 = _card()
        col2.setSpacing(6)
        col2.addWidget(_kicker("Vision"))
        try:
            from config.ollama import OLLAMA_VISION_MODEL
            vm = OLLAMA_VISION_MODEL
        except Exception:
            vm = "a local vision model"
        col2.addWidget(_body(f"{vm} — for reading images and your screen.",
                             style.INK_SOFT, 14))
        self.add(card2)
        self.end()


# ══ privacy ════════════════════════════════════════════════

class PrivacyPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__("Privacy",
                         "Mike is built to stay yours.", parent)
        card, col = _card()
        col.setSpacing(10)
        col.addWidget(_body(
            "Everything Mike does happens on this machine. The model runs "
            "locally, your files are read locally, and nothing — not your "
            "messages, not your screen, not your memory — is sent to any "
            "server. There is no account and no telemetry.", style.INK, 14))
        self.add(card)

        card2, col2 = _card()
        col2.setSpacing(10)
        col2.addWidget(_kicker("Before Mike changes anything"))
        col2.addWidget(_body(
            "Mike asks first before doing anything it can't quietly undo — "
            "sending a message, deleting a file, buying something. You approve "
            "each one, in the moment.", style.INK_SOFT, 13))
        self.add(card2)

        card3, col3 = _card()
        col3.setSpacing(6)
        col3.addWidget(_kicker("Where your data lives"))
        try:
            from config import preferences
            from brain import memory_store
            col3.addWidget(_body(f"Preferences · {preferences.path()}", style.INK_MUTE, 12))
            col3.addWidget(_body(f"Memory · {memory_store.db_path()}", style.INK_MUTE, 12))
        except Exception:
            pass
        self.add(card3)
        self.end()


# ══ about ══════════════════════════════════════════════════

class AboutPage(Page):
    def __init__(self, parent=None) -> None:
        super().__init__("About Mike", "", parent)
        card, col = _card()
        col.setSpacing(10)
        col.addWidget(_body(
            "Mike is a personal assistant that lives on your computer and can "
            "actually use it — open apps, find and write files, read your "
            "screen, fix code, and remember what matters. Not a chat window: a "
            "presence on your machine.", style.INK, 15))
        self.add(card)

        card2, col2 = _card()
        col2.setSpacing(4)
        col2.addWidget(_kicker("Version"))
        col2.addWidget(_body("Mike 1.0.0 · Windows", style.INK_SOFT, 14))
        self.add(card2)
        self.end()
