"""The composer — where you talk to Mike.

One rounded surface along the bottom of the conversation: files you've added
sit at its top as chips, the message grows as you type (Enter sends,
Shift+Enter starts a new line — students paste code and multi-line questions),
and a row of controls runs underneath: attach, talk, and the one button that
matters. That button is Send when there is something to send and becomes Stop
the moment Mike is working or speaking, so "how do I make him stop?" always
has an answer on screen, not just Esc.

The mic tells the truth about voice: a filled accent disc while it's actually
recording, a turning ring while your words are transcribed, a speaker while
Mike is talking (click to interrupt and talk). A slim status line above the
text says the same thing in words.

It keeps the exact contract UIController already drives (submitted,
attach_requested, voice.clicked_voice / voice.set_state, set_enabled, focus,
set_listening, set_responding), plus stop_requested for the Stop button.
"""
from __future__ import annotations

import math
import os

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.workspace.icons import IconButton, draw

PLACEHOLDER = "Ask Mike anything, or tell him what to do"
BUSY_PLACEHOLDER = "Mike is working — press Stop or Esc to interrupt"


class MicButton(IconButton):
    """The talk button. Its look follows the real voice state."""

    clicked_voice = Signal()

    _TIPS = {
        "idle": "Talk to Mike (F6)",
        "recording": "Listening — click when you're done",
        "transcribing": "Transcribing what you said…",
        "speaking": "Interrupt Mike and talk",
    }

    def __init__(self, parent=None) -> None:
        super().__init__("mic", self._TIPS["idle"], size=34, icon_size=19, parent=parent)
        self._vstate = "idle"
        self._t = 0.0
        self._anim = QTimer(self)
        self._anim.setInterval(33)
        self._anim.timeout.connect(self._tick)
        self.clicked.connect(self.clicked_voice.emit)
        self._listeners: list = []

    def on_state(self, callback) -> None:
        self._listeners.append(callback)

    def voice_state(self) -> str:
        return self._vstate

    #: Page states that say nothing about the microphone. The page goes to
    #: "thinking" the moment transcription starts; letting that reset the mic
    #: hid "Transcribing…" exactly while it was happening.
    _NOT_VOICE = {"thinking", "working", "responding", "needs_user", "error", "done"}

    def set_state(self, state: str) -> None:
        """Takes both page states and raw voice states; shows the voice ones."""
        if state in self._NOT_VOICE:
            return
        mapped = {
            "recording": "recording", "listening": "recording",
            "transcribing": "transcribing",
            "speaking": "speaking",
        }.get(state, "idle")
        if mapped == "speaking":
            try:
                from config import preferences
                if not preferences.get("voice_enabled", True):
                    mapped = "idle"
            except Exception:
                pass
        if mapped == self._vstate:
            return
        self._vstate = mapped
        self.setToolTip(self._TIPS[mapped])
        if mapped in ("recording", "transcribing") and not style.reduced_motion():
            self._anim.start()
        else:
            self._anim.stop()
        self.update()
        for cb in self._listeners:
            try:
                cb(mapped)
            except Exception:
                pass

    def _tick(self) -> None:
        self._t += 0.033
        if self._vstate == "recording":
            from voice import levels
            v = min(1.0, max(0.0, levels.MIC.level() - 0.12) / 0.88) ** 0.6
            self._env += (v - self._env) * (0.5 if v > self._env else 0.12)
        self.update()

    _env = 0.0

    def paintEvent(self, e) -> None:
        if self._vstate == "idle":
            super().paintEvent(e)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        acc = QColor(style.accent())
        s = self._icon_size
        icon_r = QRectF((w - s) / 2, (h - s) / 2, s, s)
        c = QRectF(0, 0, w, h).center()
        if self._vstate == "recording":
            # Filled: the mic is live. The ring around it swells with your
            # actual voice — still when you're quiet — so you can see you're
            # being heard.
            r = w / 2 - 4.5
            ring = QColor(acc)
            ring.setAlphaF(0.30 + 0.45 * self._env)
            p.setPen(QPen(ring, 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, r + 1.5 + 2.5 * self._env, r + 1.5 + 2.5 * self._env)
            p.setPen(Qt.NoPen)
            p.setBrush(acc)
            p.drawEllipse(c, r, r)
            draw(p, "mic", icon_r.adjusted(1, 1, -1, -1), QColor("#17140F"), 1.8)
        elif self._vstate == "transcribing":
            track = QColor(acc)
            track.setAlpha(46)
            p.setPen(QPen(track, 1.8))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, w / 2 - 3, w / 2 - 3)
            arc = QPen(acc, 1.8)
            arc.setCapStyle(Qt.RoundCap)
            p.setPen(arc)
            p.drawArc(QRectF(3, 3, w - 6, h - 6), int(-self._t * 320 * 16), -80 * 16)
            draw(p, "mic", icon_r, acc)
        else:  # speaking: clicking interrupts and talks
            if self._hover:
                tile = QColor(style.INK)
                tile.setAlpha(18)
                p.setPen(Qt.NoPen)
                p.setBrush(tile)
                p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)
            draw(p, "mic", icon_r, acc)


class _ComposeField(QPlainTextEdit):
    """The message itself: grows with what you write, up to a limit."""

    submit = Signal()
    files_dropped = Signal(list)
    resized = Signal()

    MAX_LINES = 8

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.setFont(style.font(style.READ - 1))
        self.document().setDocumentMargin(2)
        self.setPlaceholderText(PLACEHOLDER)
        self._busy = False
        self.textChanged.connect(self._fit)
        self._fit()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.setReadOnly(busy)
        self.setPlaceholderText(BUSY_PLACEHOLDER if busy else PLACEHOLDER)
        self.viewport().update()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            if not self._busy:
                self.submit.emit()
            return
        super().keyPressEvent(e)

    # Dropping a file onto the text inserted its path as text; attach it instead.
    def canInsertFromMimeData(self, source) -> bool:  # noqa: N802 - Qt API
        if source.hasUrls() and any(u.isLocalFile() for u in source.urls()):
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source) -> None:  # noqa: N802 - Qt API
        files = [u.toLocalFile() for u in source.urls() if u.isLocalFile()] if source.hasUrls() else []
        if files:
            self.files_dropped.emit(files)
            return
        super().insertFromMimeData(source)

    def _line_h(self) -> int:
        return self.fontMetrics().lineSpacing()

    def _fit(self) -> None:
        # A plain-text document measures its height in (wrapped) lines.
        lines = max(1, min(self.MAX_LINES, int(round(self.document().size().height()))))
        h = lines * self._line_h() + 2 * int(self.document().documentMargin()) + 4
        if self.height() != h:
            self.setFixedHeight(h)
            self.resized.emit()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        QTimer.singleShot(0, self._fit)


class _FileChip(QFrame):
    """A file queued to send, shown inside the composer until it's sent."""

    removed = Signal(str)

    def __init__(self, path: str, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self.setObjectName("fileChip")
        self.setToolTip(path)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 4, 5)
        row.setSpacing(8)
        icon = _ChipIcon(os.path.splitext(path)[1].lower())
        row.addWidget(icon, 0, Qt.AlignVCenter)
        name = os.path.basename(path)
        label = QLabel()
        label.setFont(style.font(style.SMALL, QFont.Weight.Medium))
        label.setStyleSheet(f"color:{style.INK};background:transparent;")
        label.setText(label.fontMetrics().elidedText(name, Qt.ElideMiddle, 220))
        row.addWidget(label, 0, Qt.AlignVCenter)
        x = IconButton("close", "Remove", size=22, icon_size=12)
        x.clicked.connect(lambda: self.removed.emit(self._path))
        row.addWidget(x, 0, Qt.AlignVCenter)
        self.setStyleSheet(
            f"QFrame#fileChip{{background:{style.GROUND_RAISED};"
            f"border:1px solid {style.HAIRLINE};border-radius:10px;}}")


class _ChipIcon(QWidget):
    _IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}
    _CODE = {".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".html", ".css", ".json"}

    def __init__(self, ext: str, parent=None) -> None:
        super().__init__(parent)
        self._ext = ext
        self.setFixedSize(26, 26)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        tile = QColor(style.accent())
        tile.setAlpha(40)
        p.setPen(Qt.NoPen)
        p.setBrush(tile)
        p.drawRoundedRect(QRectF(0, 0, 26, 26), 7, 7)
        name = "code" if self._ext in self._CODE else ("palette" if self._ext in self._IMAGE else "doc")
        ink = QColor(style.accent()).darker(130) if not style.is_dark() else QColor(style.accent())
        draw(p, name, QRectF(5, 5, 16, 16), ink, 1.6)


class _VoicePanel(QWidget):
    """What voice is doing, drawn and said: the nib's trace of the sound, with
    one quiet line of words above it."""

    _TEXT = {
        "recording": "Listening — pause when you're done, or click the mic",
        "transcribing": "Writing down what you said…",
        "speaking": "Speaking — press Esc to stop, or click the mic to talk",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from ui.workspace.voicetrace import VoiceTrace
        col = QVBoxLayout(self)
        col.setContentsMargins(2, 2, 0, 0)
        col.setSpacing(2)
        self._label = QLabel("")
        self._label.setFont(style.font(style.CAPTION, QFont.Weight.Medium))
        self._label.setStyleSheet(f"color:{style.INK_SOFT};background:transparent;")
        col.addWidget(self._label)
        self.trace = VoiceTrace()
        col.addWidget(self.trace)
        self._state = "idle"
        self.hide()

    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        self._state = state
        text = self._TEXT.get(state)
        if not text:
            self.trace.set_mode("off")
            self.hide()
            return
        self._label.setText(text)
        if state == "recording":
            self.trace.set_compact(False)
            self.trace.set_mode("listen")
        elif state == "transcribing":
            self.trace.set_mode("read")
        else:
            self.trace.set_compact(True)
            self.trace.set_mode("speak")
        self.show()


class Composer(QFrame):
    submitted = Signal(str)
    attach_requested = Signal(list)
    attachment_removed = Signal(str)
    stop_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("composer")
        self._responding = False
        self._listening = False
        self._has_files = False
        self._focused = False

        col = QVBoxLayout(self)
        col.setContentsMargins(14, 10, 10, 10)
        col.setSpacing(6)

        self._status = _VoicePanel()
        col.addWidget(self._status)

        self._chips = QWidget()
        self._chips_row = QHBoxLayout(self._chips)
        self._chips_row.setContentsMargins(0, 2, 0, 2)
        self._chips_row.setSpacing(6)
        self._chips_row.addStretch(1)
        self._chips.hide()
        col.addWidget(self._chips)

        self._field = _ComposeField()
        self._field.submit.connect(self._emit)
        self._field.files_dropped.connect(self.attach_requested.emit)
        self._field.textChanged.connect(self._sync_send)
        self._field.installEventFilter(self)
        self._field.setStyleSheet(
            f"QPlainTextEdit{{background:transparent;border:none;color:{style.INK};"
            f"selection-background-color:{style.accent()};padding:0 2px;}}")
        col.addWidget(self._field)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self._attach = IconButton("attach", "Attach a PDF, document, image or code file",
                                  size=34, icon_size=19)
        self._attach.clicked.connect(self._pick_files)
        row.addWidget(self._attach)
        self.voice = MicButton()
        self.voice.on_state(self._on_voice_state)
        row.addWidget(self.voice)
        row.addStretch(1)
        self._send = IconButton("send", "Send (Enter)", size=34, icon_size=18, variant="primary")
        self._send.clicked.connect(self._on_send_clicked)
        row.addWidget(self._send)
        col.addLayout(row)

        self._restyle()
        self._sync_send()

    # ── look ──────────────────────────────────────────────
    def _restyle(self) -> None:
        if self._listening:
            border = style.accent()
        elif self._focused:
            border = style.INK_MUTE
        else:
            border = style.HAIRLINE
        self.setStyleSheet(
            f"QFrame#composer{{background:{style.SURFACE};"
            f"border:1px solid {border};border-radius:18px;}}")

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if obj is self._field and event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            self._focused = event.type() == QEvent.FocusIn
            self._restyle()
        return super().eventFilter(obj, event)

    def _on_voice_state(self, state: str) -> None:
        self._status.set_state(state)
        # While you speak, the trace takes the message's place (your draft is
        # kept and comes back); while Mike speaks, you can still type.
        self._field.setVisible(state not in ("recording", "transcribing"))

    def _sync_send(self) -> None:
        if self._responding:
            self._send.set_icon("stop")
            self._send.set_variant("solid")
            self._send.setToolTip("Stop Mike (Esc)")
            self._send.setEnabled(True)
            return
        self._send.set_icon("send")
        self._send.set_variant("primary")
        self._send.setToolTip("Send (Enter)")
        has = bool(self._field.toPlainText().strip()) or self._has_files
        self._send.setEnabled(has and not self._field.isReadOnly())

    # ── contract ──────────────────────────────────────────
    def _emit(self) -> None:
        # Submit even with no text when files are queued; the page owns the
        # queue, so it decides whether there's anything to send.
        text = self._field.toPlainText().strip()
        if not text and not self._has_files:
            return
        self.submitted.emit(text)
        self._field.clear()

    def _on_send_clicked(self) -> None:
        if self._responding:
            self.stop_requested.emit()
        else:
            self._emit()

    def _pick_files(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add files for Mike", "",
            "Documents, images & code (*.pdf *.docx *.pptx *.txt *.md *.csv *.json "
            "*.py *.js *.ts *.java *.c *.cpp *.html *.css "
            "*.png *.jpg *.jpeg *.gif *.webp);;All files (*)")
        if paths:
            self.attach_requested.emit(list(paths))

    def set_attachments(self, paths: list[str]) -> None:
        while self._chips_row.count() > 1:
            item = self._chips_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        for path in paths:
            chip = _FileChip(path)
            chip.removed.connect(self.attachment_removed.emit)
            self._chips_row.insertWidget(self._chips_row.count() - 1, chip)
        self._has_files = bool(paths)
        self._chips.setVisible(self._has_files)
        self._sync_send()

    def set_text(self, text: str) -> None:
        """Start a message for the user (a suggestion they can finish)."""
        self._field.setPlainText(text)
        cursor = self._field.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._field.setTextCursor(cursor)
        self.focus()

    def text(self) -> str:
        return self._field.toPlainText()

    def set_enabled(self, enabled: bool) -> None:
        self._field.set_busy(not enabled)
        self._attach.setEnabled(enabled)
        self._sync_send()

    def focus(self) -> None:
        self._field.setFocus()

    def set_listening(self, on: bool) -> None:
        self._listening = on
        self._restyle()

    def set_responding(self, on: bool) -> None:
        self._responding = on
        self._sync_send()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return super().sizeHint()
