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

import platform
from html import escape

from PySide6.QtCore import (
    Qt, QEasingCurve, QObject, QPointF, QPropertyAnimation, QTimer, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QKeyEvent,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QTextBrowser, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel import richtext
from ui.panel.mark import PresenceMark

def _hotkey_hint() -> str:
    """The summon hotkey, as this platform's own hardware actually shows it.

    hostplatform.desktop registers Ctrl+Shift+Space on Windows and
    Cmd+Shift+Space on macOS (there is no Windows keyboard with a Cmd key,
    so the Mac symbol is meaningless there) — this mirrors those defaults
    for display rather than hardcoding one platform's hint for both.
    """
    return "Ctrl+Shift+Space" if platform.system() == "Windows" else "⌘⇧Space"


def _this_machine() -> str:
    """What to call the machine Mike runs on, in first-person copy."""
    return {"Windows": "this PC", "Darwin": "this Mac"}.get(platform.system(), "this computer")


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


class _AttachChip(QFrame):
    """A queued file, shown above the input until the turn is sent."""

    removed = Signal(str)

    def __init__(self, name: str, path: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("chip")
        self._path = path
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 3, 5, 3)
        row.setSpacing(6)
        label = QLabel(f"\U0001F4CE  {name}")
        label.setFont(style.label(11, QFont.Weight.Normal))
        label.setStyleSheet(f"color:{style.INK_SOFT};background:transparent;")
        row.addWidget(label)
        close = QPushButton("✕")
        close.setObjectName("chipx")
        close.setCursor(Qt.PointingHandCursor)
        close.setFixedSize(16, 16)
        close.clicked.connect(lambda: self.removed.emit(self._path))
        row.addWidget(close)


class _InputBar(QFrame):
    submitted = Signal(str)
    attach_requested = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inputBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 11, 12, 11)
        row.setSpacing(10)

        self.voice = _Voice()
        row.addWidget(self.voice, 0, Qt.AlignVCenter)

        # Attach a file — a document or an image — for Mike to read. A quiet
        # plus, not a loud button; the drop target is the whole panel too.
        self._attach = QPushButton("+")
        self._attach.setObjectName("attach")
        self._attach.setCursor(Qt.PointingHandCursor)
        self._attach.setFixedSize(24, 24)
        self._attach.setToolTip("Attach a PDF, document or image")
        self._attach.clicked.connect(self._pick_files)
        row.addWidget(self._attach, 0, Qt.AlignVCenter)

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

        self._hint = QLabel(_hotkey_hint())
        self._hint.setFont(style.label(10))
        self._hint.setStyleSheet(f"color:{style.INK_FAINT};background:transparent;")
        row.addWidget(self._hint, 0, Qt.AlignVCenter)

        # A breathing line of light along the bottom edge — the panel's one
        # calm, always-there sign of life. It rests as a slow, faint breath;
        # brightens and quickens while listening (you're being heard); and
        # flows left-to-right while Mike is answering (something is arriving).
        # One element carries both sides of the exchange so input and output
        # feel like the same living surface rather than two states bolted on.
        # A still, faint accent hairline under the field, shown only while Mike
        # is actually listening or answering. It eases in and out and then holds
        # -- no breathing, no travelling light. When it's idle the line is gone
        # and the timer is stopped, so the input is simply a clean field at rest.
        self._state = "idle"        # idle | listening | responding
        self._opacity = 0.0
        self._target = 0.0
        self._ease_timer = QTimer(self)
        self._ease_timer.setInterval(16)
        self._ease_timer.timeout.connect(self._ease)

    def _set_target(self, value: float) -> None:
        self._target = value
        if not self._ease_timer.isActive():
            self._ease_timer.start()

    def _ease(self) -> None:
        self._opacity += (self._target - self._opacity) * 0.16
        if abs(self._opacity - self._target) < 0.004:
            self._opacity = self._target
            if self._target == 0.0:
                self._ease_timer.stop()   # at rest: no more repaints
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._opacity <= 0.003:
            return
        w = self.width()
        y = self.height() - 3.0
        accent = QColor(style.accent())
        edge = QColor(accent); edge.setAlphaF(0.0)
        mid = QColor(accent); mid.setAlphaF(self._opacity)
        grad = QLinearGradient(16.0, 0.0, float(w - 16), 0.0)
        grad.setColorAt(0.0, edge)
        grad.setColorAt(0.5, mid)
        grad.setColorAt(1.0, edge)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QBrush(grad), 1.3))
        p.drawLine(QPointF(16.0, y), QPointF(float(w - 16), y))

    def _pick_files(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach files for Mike", "",
            "Documents & images (*.pdf *.docx *.pptx *.txt *.md *.csv *.json "
            "*.py *.js *.png *.jpg *.jpeg *.gif *.webp);;All files (*)")
        if paths:
            self.attach_requested.emit(list(paths))

    def _emit(self) -> None:
        # Submit even with no text if the field is empty but files are queued;
        # the panel owns the queue, so it also decides whether there's anything
        # to send. Here we just forward the words (possibly "").
        self.submitted.emit(self._field.text().strip())
        self._field.clear()

    def set_enabled(self, enabled: bool) -> None:
        self._field.setEnabled(enabled)
        self._field.setPlaceholderText(
            "Ask Mike, or hold to talk" if enabled else "Mike is working…")

    def focus(self) -> None:
        self._field.setFocus()

    _LISTEN_OPACITY = 0.26
    _RESPOND_OPACITY = 0.16

    def set_listening(self, on: bool) -> None:
        self._field.setPlaceholderText("Listening…" if on else "Ask Mike, or hold to talk")
        if on:
            self._state = "listening"
            self._set_target(self._LISTEN_OPACITY)
        elif self._state == "listening":
            self._state = "idle"
            self._set_target(0.0)

    def set_responding(self, on: bool) -> None:
        """Mike is answering: the line holds, faint, until he's done."""
        if on:
            self._state = "responding"
            self._set_target(self._RESPOND_OPACITY)
        elif self._state == "responding":
            self._state = "idle"
            self._set_target(0.0)


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


class _RichTurn(QTextBrowser):
    """Mike's message, rendered rather than escaped.

    A QTextBrowser (Qt's own rich-text engine, no web view) showing the
    Markdown Mike actually writes -- headings, lists, tables, and
    syntax-highlighted code with a one-click copy link. Sizes itself to its
    content so it sits in the conversation column like any other block, with no
    inner scrollbar of its own.
    """

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._raw = text
        self._codes: list[str] = []
        # A finished reply (not one still streaming) carries a quiet "Copy"
        # for the whole answer — the thing a student most often wants to do
        # with it after reading.
        self._final = bool(text)
        self._copied = False
        # True while tokens are arriving — the pen that writes the reply
        # follows the text only while this is set.
        self._streaming = False
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.setStyleSheet("QTextBrowser{background:transparent;border:none;}")
        self.document().setDocumentMargin(0)
        self.anchorClicked.connect(self._on_anchor)
        # A short coalescing timer so a burst of tokens is one repaint, not one
        # per character; the trailing render always lands.
        self._pending = QTimer(self)
        self._pending.setSingleShot(True)
        self._pending.setInterval(70)
        self._pending.timeout.connect(lambda: self._render(do_highlight=False))
        self._render()

    def _render(self, do_highlight: bool = True) -> None:
        html, self._codes = richtext.render(self._raw, do_highlight=do_highlight)
        if self._final and self._raw.strip():
            label = "✓ Copied" if self._copied else "Copy"
            html += (
                f'<p style="margin-top:2px; margin-bottom:0;">'
                f'<a href="copyall://reply" style="color:{style.INK_MUTE}; '
                f'font-family:{style.ui_family()}; font-size:12px; '
                f'text-decoration:none;">{label}</a></p>')
        self.setHtml(html)
        self._fit_height()

    def _fit_height(self) -> None:
        doc = self.document()
        # Before the first layout the viewport has no real width; a fallback
        # near the column's own width keeps the initial height estimate sane so
        # the panel doesn't jump from a one-pixel-wide, very tall guess.
        width = self.viewport().width()
        if width < 50:
            width = 560
        doc.setTextWidth(width)
        self.setFixedHeight(int(doc.size().height()) + 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_height()

    def append_text(self, chunk: str) -> None:
        # Streaming: coalesce, and skip highlighting until the reply settles.
        self._streaming = True
        self._raw += chunk
        if not self._pending.isActive():
            self._pending.start()

    def set_text(self, text: str, final: bool = True) -> None:
        # The final word: stop any pending stream render and do the full,
        # syntax-highlighted pass. `final=False` for a sentence Mike said on
        # the way to doing something — rendered, but not offered for copying.
        self._raw = text
        self._final = final
        self._streaming = False
        self._pending.stop()
        self._render(do_highlight=True)

    def text(self) -> str:
        return self._raw

    def _on_anchor(self, url) -> None:
        scheme = url.scheme()
        if scheme == "copyall":
            QApplication.clipboard().setText(self._raw)
            self._copied = True
            self._render(do_highlight=True)

            def _reset() -> None:
                self._copied = False
                self._render(do_highlight=True)
            QTimer.singleShot(1600, self, _reset)
            return
        if scheme == "copy":
            try:
                index = int(url.toString().split("copy://", 1)[1])
            except (ValueError, IndexError):
                return
            if 0 <= index < len(self._codes):
                QApplication.clipboard().setText(self._codes[index])
        elif scheme in ("http", "https"):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)


# ══ the wait ═══════════════════════════════════════════════

#: What Mike says he's doing while you wait.
#:
#: A local model on a laptop takes real seconds to answer, and a single
#: frozen "Thinking…" for all of them reads as a hang -- the user cannot
#: tell a model that is working from one that has died. Rotating the word
#: is the cheapest honest signal that something is still happening: it
#: changes because time is passing, which is exactly what it claims.
#:
#: Chosen to sound like Mike rather than like a loading bar -- the register
#: is a person half-answering you from the next room, not a system reporting
#: status. Deliberately no ironic or cutesy entries: this shows up when
#: somebody is waiting, and a joke wears out on the fourth reading.
THINKING_WORDS = (
    "Thinking",
    "Pondering",
    "Percolating",
    "Triangulating",
    "Noodling",
    "Untangling",
    "Ruminating",
    "Mulling it over",
    "Piecing it together",
    "Following the thread",
    "Turning it over",
    "Chewing on it",
    "Puzzling it out",
    "Marinating",
    "Cogitating",
    "Wrangling",
    "Tinkering",
    "Simmering",
    # The tail: held back for waits long enough that novelty stops helping
    # and reassurance starts. Kept last on purpose -- see _next_word.
    "Getting there",
    "Nearly there",
)

#: How many of the above are the reassuring tail rather than the playful body.
_REASSURING_TAIL = 2


class _Thinking(QWidget):
    """The gap between asking and answering, made to feel inhabited.

    Three things move, on purpose, at three different rates:

    - the word, every few seconds, so a long wait visibly progresses rather
      than repeating;
    - the ellipsis, about twice a second, the small constant tick that says
      the process is alive between word changes;
    - the accent dot, breathing on a slow sine, which is the same living
      mark the ledger already uses for a step in flight.

    The last two words of THINKING_WORDS ("Getting there", "Nearly there")
    are held back for waits long enough to need reassurance rather than
    novelty, so the copy tracks the actual situation instead of cycling
    forever through synonyms.
    """

    _WORD_MS = 2800
    _FRAME_MS = 16          # ~60fps, so nothing about this reads as stepping
    _LONG_WAIT_MS = 11_000

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._index = 0
        self._t = 0.0          # seconds, continuous — every motion derives from this
        self._elapsed = 0
        self.setFixedHeight(30)

        self._frame = QTimer(self)
        self._frame.timeout.connect(self._on_frame)
        self._frame.start(self._FRAME_MS)

        self._rotate = QTimer(self)
        self._rotate.timeout.connect(self._next_word)
        self._rotate.start(self._WORD_MS)

    def stop(self) -> None:
        """Animations hold a timer against a widget the panel is about to
        delete; stopping them explicitly keeps a timeout from firing into a
        half-torn-down widget."""
        self._frame.stop()
        self._rotate.stop()

    def _on_frame(self) -> None:
        self._t += self._FRAME_MS / 1000.0
        self._elapsed += self._FRAME_MS
        self.update()

    def _next_word(self) -> None:
        body = len(THINKING_WORDS) - _REASSURING_TAIL
        if self._elapsed >= self._LONG_WAIT_MS:
            # Past the point where novelty stops helping: stay on the
            # reassuring tail rather than implying fresh activity.
            self._index = body + ((self._index + 1) % _REASSURING_TAIL)
        else:
            # Shuffled rather than sequential, so two waits in a row don't
            # read as the same canned loop -- but never repeating the word
            # currently on screen, which would look like it had frozen.
            import random

            choice = self._index
            while choice == self._index and body > 1:
                choice = random.randrange(body)
            self._index = choice
        # word swap is not a paint trigger on its own -- the frame timer already
        # repaints ~60x/s, so there is nothing to force here.

    def paintEvent(self, _e) -> None:
        import math

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        cx, cy = 6.0, self.height() / 2.0
        accent = style.qaccent()

        # One quiet dot, breathing gently. No ring, no pulse -- the restraint is
        # the point; a single mark that's alive reads as premium where a sonar
        # ping reads as a toy.
        breath = 0.5 + 0.32 * (0.5 + 0.5 * math.sin(self._t * 1.7))
        core = QColor(accent)
        core.setAlphaF(breath)
        p.setPen(Qt.NoPen)
        p.setBrush(core)
        p.drawEllipse(QPointF(cx, cy), 2.6, 2.6)

        # The word, with a soft highlight passing through it -- subtle enough to
        # be a sign of life, not a spinner.
        word = THINKING_WORDS[self._index]
        font = style.voice(15)
        p.setFont(font)
        fm = p.fontMetrics()
        tx = cx + 3.2 + 12.0
        tw = max(1.0, float(fm.horizontalAdvance(word)))
        baseline = cy + (fm.ascent() - fm.descent()) / 2.0

        base = QColor(style.INK_MUTE)
        bright = QColor(style.INK_SOFT)          # a whisper of lift, not a flash
        sweep = (self._t * 0.5) % 1.9            # slower, with a longer pause
        grad = QLinearGradient(tx, 0.0, tx + tw, 0.0)
        grad.setColorAt(0.0, base)
        if 0.0 <= sweep <= 1.0:
            half = 0.16
            lo = max(0.001, sweep - half)
            hi = min(0.999, sweep + half)
            mid = min(max(sweep, lo + 0.001), hi - 0.001)
            grad.setColorAt(lo, base)
            grad.setColorAt(mid, bright)
            grad.setColorAt(hi, base)
        grad.setColorAt(1.0, base)

        # Filled as a path, not drawn with a pen: text drawn through a gradient
        # pen is silently flat on some Qt builds, but a filled glyph path takes
        # the gradient reliably.
        path = QPainterPath()
        path.addText(QPointF(tx, baseline), font, word)
        p.fillPath(path, QBrush(grad))


def _animate_entry(widget: QWidget) -> None:
    """Fade a new line in instead of having it appear between frames.

    The panel grows to fit its content, so without this every message is a
    hard cut: the window jumps taller and fully-formed text is simply
    present. A short fade (and a few pixels of rise) makes it read as
    arriving, which is the same reason MikeWindow animates the panel itself
    in rather than showing it. Kept under 200ms -- this is meant to soften a
    transition, never to make anyone wait for it.

    The effect and animation are parented to the widget so they live exactly
    as long as it does.
    """
    try:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", widget)
        fade.setDuration(180)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        # Parented to the widget, so the widget owns it and it dies with it.
        # Deliberately NOT DeleteWhenStopped: combining the two gives the
        # animation two owners, and the second delete is an access violation
        # with no Python traceback -- which is exactly how this first
        # shipped, crashing the moment a test pumped the event loop while a
        # panel was being torn down.
        fade.start()
    except Exception:
        # A missing animation must never cost the message itself.
        pass


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

    def set_text(self, index: int, text: str) -> None:
        """Updates a row's own label in place — for a step whose duration
        is real and worth narrating (a multi-minute model download) rather
        than one whose name is decided once at the start and never changes."""
        if 0 <= index < len(self._rows):
            self._rows[index] = (text, self._rows[index][1])
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

    def update_text(self, text: str) -> None:
        self._label = _PlainText(text)
        self._ledger.set_text(self._index, text)


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
        col.setContentsMargins(17, 15, 17, 15)
        col.setSpacing(11)

        head = QHBoxLayout(); head.setSpacing(9)
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color:{style.WARN};background:transparent;font-size:9px;")
        head.addWidget(self._dot, 0, Qt.AlignVCenter)
        self._head = QLabel("MIKE WANTS TO")
        self._head.setFont(style.label(10))
        self._head.setStyleSheet(
            f"color:{style.WARN};background:transparent;letter-spacing:1.6px;")
        head.addWidget(self._head, 1, Qt.AlignVCenter)
        col.addLayout(head)

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setFont(style.voice(15))
        self._body.setStyleSheet(f"color:{style.INK};background:transparent;")
        col.addWidget(self._body)

        # a distinct consequence line — shown only when the action is
        # irreversible, so "you can't take this back" is impossible to miss.
        self._consequence = QLabel()
        self._consequence.setWordWrap(True)
        self._consequence.setFont(style.label(11, __import__("PySide6").QtGui.QFont.Weight.Normal))
        self._consequence.setStyleSheet(f"color:{style.STOP};background:transparent;")
        self._consequence.hide()
        col.addWidget(self._consequence)

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

    # keywords that make an action irreversible / weightier — used ONLY to
    # shape how clearly the panel warns, never to decide anything. The real
    # gate is in the engine; this just makes sure a delete never looks like a
    # casual amber button.
    _DESTRUCTIVE = ("delete", "remove", "erase", "overwrite", "permanent",
                    "can't be undone", "cannot be undone", "irreversible")
    _VERB = {"delete": "Delete", "remove": "Remove", "send": "Send",
             "email": "Send", "overwrite": "Overwrite", "move": "Move"}

    def ask(self, description: str) -> None:
        lower = description.lower()
        destructive = any(k in lower for k in self._DESTRUCTIVE)

        verb = "Go ahead"
        for key, label in self._VERB.items():
            if key in lower:
                verb = label
                break

        # the irreversibility clause moves to its own red line, so strip it
        # from the body rather than saying it twice.
        body = description
        for clause in ("This can't be undone.", "This cannot be undone.",
                       "This can't be undone", "This cannot be undone",
                       "This is permanent.", "This is permanent"):
            body = body.replace(clause, "").replace("  ", " ").strip(" —-.")
        if body and not body.endswith((".", "?", "!")):
            body += "."

        self._head.setText("MIKE WANTS TO" if verb != "Go ahead" else "MIKE NEEDS YOU")
        self._body.setText(body)
        self._allow.setText(verb)
        # destructive → the affirmative is red and deliberate, not inviting.
        self._allow.setObjectName("allow_danger" if destructive else "allow")
        self._allow.style().unpolish(self._allow); self._allow.style().polish(self._allow)

        if destructive:
            self._consequence.setText("This can't be undone.")
            self._consequence.show()
        else:
            self._consequence.hide()

        # a matching accent on the block's edge
        self.setProperty("danger", destructive)
        self.style().unpolish(self); self.style().polish(self)

        self.show()
        self.visibility_changed.emit()

    def hide(self) -> None:  # noqa: A003 - matches the controller contract
        super().hide()
        self.visibility_changed.emit()


# ══ first run: something to actually try ═══════════════════

#: Four things a new user can click on their first launch.
#:
#: Chosen against one rule: every one of these has been verified working
#: end-to-end on Windows. A starter suggestion that fails is worse than no
#: suggestion at all -- it is the first thing the user ever asks Mike to do,
#: and it decides whether they believe the rest of the claims. So no wake
#: word (not implemented on Windows), no scrolling or dragging (honestly
#: unsupported), nothing destructive, and nothing that opens a paid app.
#:
#: They are also deliberately a spread rather than four of the same thing:
#: something visible happens on screen, something shows he can see, something
#: shows he writes real code, something shows he remembers. Between them
#: they answer "what is this?" far better than a paragraph of prose does.
STARTERS = (
    ("Open YouTube", "open youtube.com"),
    ("Look at my screen", "what's on my screen right now?"),
    ("Write me something", "write me a short study plan for this week and "
                           "save it on my desktop"),
    ("Remember this", "remember that I'm learning Python this term"),
)


class _Starters(QWidget):
    """Clickable openers, shown once, on the first launch only.

    The panel already had a `suggestion_clicked` signal wired all the way
    through to the controller's process_message -- and nothing that ever
    emitted it. This is the missing half: the wiring was built for a feature
    that was never given a face.

    They disappear the moment one is used or anything is typed, because
    their whole job is to get the first message sent. After that they would
    just be clutter in a surface whose entire design is "exactly as large as
    the moment needs".
    """

    picked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        row = QVBoxLayout(self)
        row.setContentsMargins(0, 12, 0, 2)
        row.setSpacing(7)

        # Without this the chips read as buttons whose purpose is unclear.
        # Naming them as an invitation is what turns "what is this app?" into
        # a first message being sent.
        prompt = QLabel("Try one —")
        prompt.setFont(style.label(10))
        prompt.setStyleSheet(
            f"color:{style.INK_MUTE};background:transparent;padding-bottom:2px;")
        row.addWidget(prompt)

        line = QHBoxLayout()
        line.setSpacing(7)
        line.setContentsMargins(0, 0, 0, 0)
        for index, (label, prompt) in enumerate(STARTERS):
            chip = QPushButton(label)
            chip.setObjectName("starter")
            chip.setCursor(Qt.PointingHandCursor)
            chip.setFont(style.label(11))
            chip.clicked.connect(lambda _=False, p=prompt: self.picked.emit(p))
            line.addWidget(chip, 0, Qt.AlignLeft)
            # Two per line: four chips in a row would each be too narrow to
            # read at this panel's width.
            if index % 2 == 1:
                line.addStretch(1)
                row.addLayout(line)
                line = QHBoxLayout()
                line.setSpacing(7)
                line.setContentsMargins(0, 0, 0, 0)
        if line.count():
            line.addStretch(1)
            row.addLayout(line)


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
        self._section("PRIVACY", f"Everything Mike does stays on {_this_machine()}. "
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
        # "Samantha" is macOS's own native voice; naming it unconditionally
        # here on Windows told a real user their voice was still "Samantha"
        # when it was actually SAPI5 -- a name that means nothing on this
        # platform and reads as broken, not just wrong. voice.providers
        # already knows which native backend this machine actually has and
        # can describe it (name and all); ask it rather than hardcode
        # either platform's answer here.
        try:
            from voice.providers import native_provider_class
            ok, why = native_provider_class()().available()
            if ok:
                return f"{why}. Always available."
        except Exception:
            pass
        return "The built-in system voice. Always available."

    def _model_line(self) -> str:
        try:
            from config.ollama import OLLAMA_CHAT_MODEL
            return f"Recommended for {_this_machine()}. Running {OLLAMA_CHAT_MODEL}, entirely on-device."
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
    #: Emitted whenever Mike's state changes, so the window can give an
    #: ambient signal (a menu-bar notification) when something happens while
    #: the panel is hidden.
    state_changed = Signal(str)

    #: Emitted when the user clicks the close button in the header. The
    #: panel itself has no title bar (it's frameless -- see
    #: MikeWindow._configure_window) and, before this button existed, the
    #: only way to put it away was the global hotkey or Escape-cancelling
    #: active work -- neither discoverable to someone who just summoned Mike
    #: by typing. MikeWindow owns what "close" actually does (the same fade
    #: -out used when the hotkey dismisses it), so this only asks.
    dismiss_requested = Signal()
    #: The window (MikeWindow) owns what these do; the panel only asks, so the
    #: frameless surface gets the same minimise / maximise the OS chrome would
    #: give a normal window.
    minimise_requested = Signal()
    maximise_requested = Signal()

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

        # Minimise and maximise. The surface is frameless, so it carries its own
        # window controls the way the OS chrome would -- a matched set with the
        # close box, in the same quiet weight so they read as chrome, not action.
        self._min_btn = QPushButton("–")     # en dash: a calm minus, not a hyphen
        self._min_btn.setObjectName("winctl")
        self._min_btn.setCursor(Qt.PointingHandCursor)
        self._min_btn.setFixedSize(28, 24)
        self._min_btn.setToolTip("Minimise")
        self._min_btn.clicked.connect(self.minimise_requested.emit)
        hb.addWidget(self._min_btn, 0, Qt.AlignVCenter)

        self._max_btn = QPushButton("▢")     # a light square: maximise / restore
        self._max_btn.setObjectName("winctl")
        self._max_btn.setCursor(Qt.PointingHandCursor)
        self._max_btn.setFixedSize(28, 24)
        self._max_btn.setToolTip("Maximise")
        self._max_btn.clicked.connect(self.maximise_requested.emit)
        hb.addWidget(self._max_btn, 0, Qt.AlignVCenter)

        # A real close button. The window is frameless (no OS title bar, no
        # OS close box), and the only other way to put Mike away -- the
        # global hotkey -- is invisible unless you already know it exists.
        # Every other control on this surface is reached by clicking
        # something; closing shouldn't be the one exception.
        self._close_btn = QPushButton("✕")
        self._close_btn.setObjectName("close")
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setFixedSize(28, 24)
        self._close_btn.setToolTip(f"Close ({_hotkey_hint()} to bring Mike back)")
        self._close_btn.clicked.connect(self.dismiss_requested.emit)
        hb.addWidget(self._close_btn, 0, Qt.AlignVCenter)
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

        # attachment chips: a quiet row just above the input, present only when
        # something is queued to send.
        self._attachments: list[str] = []
        self._chips = QWidget()
        self._chips_row = QHBoxLayout(self._chips)
        self._chips_row.setContentsMargins(16, 0, 16, 6)
        self._chips_row.setSpacing(6)
        self._chips_row.addStretch(1)
        self._chips.hide()
        outer.addWidget(self._chips)

        # input: the anchor, always present
        self.input = _InputBar()
        self.input.attach_requested.connect(self.add_attachments)
        pad = QVBoxLayout()
        pad.setContentsMargins(14, 4, 14, 14)
        pad.addWidget(self.input)
        outer.addLayout(pad)

        # The whole panel is a drop target, not just the little plus.
        self.setAcceptDrops(True)

        self.setStyleSheet(_build_stylesheet())
        self._show_resting()

    def _restyle(self) -> None:
        """Re-apply styles so a changed accent flows through the whole panel
        live — the presence mark already reads the accent on every paint."""
        self.setStyleSheet(_build_stylesheet())
        self.mark.update()
        self.input.voice.update()

    # ── resting composition ───────────────────────────────
    def _intro(self) -> str:
        """The first thing anyone ever reads. Four questions, in order.

        Rewritten after reading it as someone who knows nothing: the old
        version was a four-line paragraph that answered "what can you do"
        with "read and write files, run commands" — mechanisms, and
        developer ones. Someone who has just installed this does not want a
        command runner, and would not know they wanted one.

        So: who he is, then what that means in things they'd actually ask
        for, then how to reach him. Short enough to be read rather than
        skimmed past, because the starter chips underneath are doing the
        real explaining.
        """
        return (
            f"I'm Mike. I live on {_this_machine()} — and unlike a chat "
            "window, I can actually use it.\n\n"
            "Open things, find files, write something, fix code that won't "
            "work. I check before changing anything, and nothing leaves "
            "this machine."
        )

    def _how_to_reach(self) -> str:
        """Said separately and quietly, because it's reference, not welcome.

        Three ways in, and the old intro mentioned two -- typing and the
        hotkey -- while the mic sat in the input bar unexplained. "Hold to
        talk" is not obvious if you have never seen it.
        """
        return f"Type below · hold the mic to talk · {_hotkey_hint()} anywhere"

    def _show_resting(self) -> None:
        from config import preferences

        first_run = not bool(preferences.get("onboarding_complete", False))
        text = self._intro() if first_run else self._greeting()
        self._resting = _Turn(text, "mike")
        self._resting.setStyleSheet("padding-top:2px;")
        self._insert(self._resting)
        if first_run:
            # Telling someone what Mike can do is weaker than letting them
            # find out in one click, so the first launch offers openers that
            # actually run rather than a longer paragraph about capabilities.
            self._starters = _Starters()
            self._starters.picked.connect(self._on_starter)
            self._insert(self._starters)

            reach = QLabel(self._how_to_reach())
            reach.setFont(style.label(10))
            # Wraps rather than running under the scrollbar: without this the
            # line was clipped mid-word on first run, which is a poor first
            # impression from the one line that explains how to talk to him.
            reach.setWordWrap(True)
            reach.setStyleSheet(
                f"color:{style.INK_MUTE};background:transparent;padding-top:4px;")
            self._reach = reach
            self._insert(reach)

            preferences.set_value("onboarding_complete", True)

    def _on_starter(self, prompt: str) -> None:
        self._drop_starters()
        self.conversation.suggestion_clicked.emit(prompt)

    def _drop_starters(self) -> None:
        for name in ("_starters", "_reach"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.hide()
                self._stage.removeWidget(widget)
                widget.deleteLater()
                setattr(self, name, None)

    def _greeting(self) -> str:
        from datetime import datetime
        h = datetime.now().hour
        part = ("Good morning." if 5 <= h < 12 else "Good afternoon."
                if 12 <= h < 17 else "Good evening." if 17 <= h < 22 else "Still here.")
        return f"{part}  Ask me anything, or press {_hotkey_hint()} to talk."

    def _drop_resting(self) -> None:
        r = getattr(self, "_resting", None)
        if r is not None:
            r.hide()
            self._stage.removeWidget(r)
            r.deleteLater()
            self._resting = None
        # The starters exist only to get the first message sent. Once the
        # user has typed or spoken one themselves they are answered, and
        # leaving them on screen would be clutter in a panel whose whole
        # design is being exactly as large as the moment needs.
        self._drop_starters()

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
        """Keep the window sized to the content — until the user takes over.

        Uses resize(), not setFixedHeight(), so the window stays draggable from
        its edges; and backs off entirely once the user has resized or
        maximised (the window flips its own auto_height off), so the fit never
        yanks a height the user chose back to the content's.
        """
        win = self.window()
        if win is None or win is self:
            return
        if not getattr(win, "_auto_height", True) or win.isMaximized():
            return
        h = self.desired_height()
        if win.height() == h:
            return
        # Flag it as ours so the window doesn't mistake this for a user resize.
        try:
            win._programmatic_resize = True
            win.resize(win.width(), h)
        finally:
            win._programmatic_resize = False

    # ── column helpers ────────────────────────────────────
    def _insert(self, widget: QWidget) -> None:
        self._stage.insertWidget(self._stage.count() - 1, widget)
        _animate_entry(widget)
        self.conversation.scroll_to_bottom()
        QTimer.singleShot(0, self._fit)

    # ── controller contract ───────────────────────────────
    def add_user_message(self, text: str, attachments: list[str] | None = None) -> None:
        self._drop_resting()
        import os

        shown = text
        if attachments:
            names = ", ".join(os.path.basename(a) for a in attachments)
            tag = f"\U0001F4CE {names}"
            shown = f"{tag}\n{text}" if text else tag
        self._insert(_Turn(shown, "you"))
        self._ledger = None

    # ── attachments ───────────────────────────────────────
    def add_attachments(self, paths: list[str]) -> None:
        import os

        for path in paths:
            if path and os.path.exists(path) and path not in self._attachments:
                self._attachments.append(path)
        self._refresh_chips()

    def take_attachments(self) -> list[str]:
        """Hand the queued files to the caller and clear the row."""
        pending = list(self._attachments)
        self._attachments.clear()
        self._refresh_chips()
        return pending

    def _refresh_chips(self) -> None:
        import os

        # Rebuild the chip row from the current queue.
        while self._chips_row.count() > 1:      # keep the trailing stretch
            item = self._chips_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for path in self._attachments:
            chip = _AttachChip(os.path.basename(path), path)
            chip.removed.connect(self._remove_attachment)
            self._chips_row.insertWidget(self._chips_row.count() - 1, chip)
        self._chips.setVisible(bool(self._attachments))
        QTimer.singleShot(0, self._fit)

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

    def begin_mike_stream(self):
        self._drop_resting()
        self._stream = _RichTurn("")
        self._insert(self._stream)
        return self._stream

    def add_mike_message(self, text: str) -> None:
        self._drop_resting()
        self._insert(_RichTurn(text))

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
        self._thinking = _Thinking()
        self._insert(self._thinking)

    def hide_thinking(self) -> None:
        if self._thinking is not None:
            # Stop its timers before the widget goes: a rotation firing into
            # a widget mid-deleteLater is a crash with no useful traceback.
            stop = getattr(self._thinking, "stop", None)
            if stop is not None:
                stop()
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
        # The input's breathing line flows while Mike is producing anything —
        # thinking, working a tool, or speaking — so output has its own calm
        # sign of life, the same element that breathes for input.
        self.input.set_responding(
            state in ("thinking", "working", "responding", "speaking"))
        self.state_changed.emit(state)

    def state(self) -> str:
        return self._state

    def set_maximised(self, on: bool) -> None:
        """Reflect the window's maximise state on the button, so it reads as a
        toggle: a single square to grow, an overlapped pair to bring back."""
        self._max_btn.setText("❐" if on else "▢")
        self._max_btn.setToolTip("Restore" if on else "Maximise")

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
        # Grow to show the settings, but with resize() rather than a fixed
        # height, so the window stays draggable and the user's own larger size
        # is left alone.
        if (win is not None and win is not self
                and not win.isMaximized() and win.height() < self.CAP_HEIGHT):
            try:
                win._programmatic_resize = True
                win.resize(win.width(), self.CAP_HEIGHT)
            finally:
                win._programmatic_resize = False

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
QPushButton#winctl {{
    background: transparent; color: {style.INK_MUTE};
    border: none; font-size: 13px; padding: 0 2px;
}}
QPushButton#winctl:hover {{ color: {style.INK}; }}
QPushButton#attach {{
    background: transparent; color: {style.INK_MUTE};
    border: none; font-size: 20px; padding: 0;
}}
QPushButton#attach:hover {{ color: {style.accent()}; }}
QFrame#chip {{
    background: {style.GROUND_SUNK};
    border: 1px solid {style.HAIRLINE};
    border-radius: 8px;
}}
QPushButton#chipx {{
    background: transparent; color: {style.INK_MUTE};
    border: none; font-size: 10px;
}}
QPushButton#chipx:hover {{ color: {style.STOP}; }}
QPushButton#close {{
    background: transparent; color: {style.INK_MUTE};
    border: none; font-size: 13px; padding: 0 2px;
}}
QPushButton#close:hover {{ color: {style.STOP}; }}
QPushButton#starter {{
    background: {style.GROUND_RAISED};
    color: {style.INK_SOFT};
    border: 1px solid {style.HAIRLINE};
    border-radius: 13px;
    padding: 6px 13px;
    text-align: left;
}}
QPushButton#starter:hover {{
    color: {style.INK};
    border-color: {style.accent()};
}}
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
QFrame#confirm[danger="true"] {{
    border: 1px solid {style.STOP};
}}
QPushButton#allow_danger {{
    background: transparent; color: {style.STOP};
    border: 1px solid {style.STOP}; border-radius: 8px;
    padding: 7px 18px; font-size: 13px; font-weight: 600;
}}
QPushButton#allow_danger:hover {{
    background: {style.STOP}; color: #17140F;
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
