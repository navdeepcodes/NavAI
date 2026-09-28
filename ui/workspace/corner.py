"""CORNER MIKE — the companion that stays when the workspace is away.

When FULL MIKE is minimised or closed, this small presence takes the corner:
the mark (alive with Mike's state), a slim line to keep talking, and — only
when there's something to say — what he's doing right now and what he said.
It never forces the whole application back over your work; it surfaces just
the relevant thing and recedes.

While Mike works, the corner says what he's doing in plain words, how long
it's been going, and offers Stop — the same trust the full window gives, in a
fraction of the space. A long answer is shown in part with a way to read the
rest in the full window, rather than clipped mid-line.

It is a whole Mike in small: above every other window while it's shown, a
mic to talk to him, draggable anywhere (and it stays where it's put), and the
approvals he asks for are answered right here — before, a question asked
while the workspace was minimised waited unseen behind "Working…".

It implements the same contract the controller already speaks to a floating
companion (activate / dismiss / set_state / show_tool_status / append_response
/ finish / message_submitted / expand_requested / cancel_requested, and ask /
hide_confirmation / answered / voice_requested for the approvals and the mic).
"""
from __future__ import annotations

import sys
import time

from PySide6.QtCore import QPoint, Qt, QRect, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from ui.panel import style
from ui.panel.mark import PresenceMark
from ui.workspace.icons import IconButton
from ui.workspace.mission_bar import MissionLine

#: How much of an answer the corner shows before offering the full window.
ANSWER_CHARS = 320
#: Where the corner was put, as "x,y" of its bottom-right corner ("" = default).
ANCHOR_PREF = "corner_anchor"

_STATE_TEXT = {
    "thinking": "Thinking…",
    "listening": "Listening…",
    "transcribing": "Transcribing…",
    "working": "Working…",
}
_BUSY = {"thinking", "working", "listening", "transcribing"}


class _CornerField(QLineEdit):
    def __init__(self, on_submit, parent=None) -> None:
        super().__init__(parent)
        self._on_submit = on_submit

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_submit()
            return
        super().keyPressEvent(e)


def _corner_confirm():
    """The workspace's approval card, with a shorter preview: the corner is
    small, and the buttons must stay within reach."""
    from ui.panel.mike_panel import _build_stylesheet
    from ui.workspace.chat_page import ConfirmCard

    class CornerConfirm(ConfirmCard):
        MAX_PREVIEW = 110

        def __init__(self) -> None:
            super().__init__()
            # its buttons are styled by the workspace's sheet, which the corner
            # doesn't carry: without it they drew as nothing at all
            self.setStyleSheet(_build_stylesheet())
            # the session-long yes ("Allow edits in NavAI this session") is a
            # line of its own here -- beside Don't and Go ahead it didn't fit
            lay = self.layout()
            for i in range(lay.count()):
                row = lay.itemAt(i).layout()
                if row is not None and row.indexOf(self._always) >= 0:
                    row.removeWidget(self._always)
                    lay.addWidget(self._always)
                    break

        def ask(self, description: str, offer: str = "") -> None:
            super().ask(description, offer)
            # measured at the corner's width, not the workspace's: "Write to
            # file: Desktop/boolean_search.py" lost its second line otherwise
            width = CornerPresence.WIDTH - 2 * CornerPresence.SHADOW - 24 - 34 - 10
            need = self._body.heightForWidth(width) + 4
            self._body_wrap.setFixedHeight(max(24, min(need, self.MAX_PREVIEW)))

    return CornerConfirm()


class CornerPresence(QWidget):

    message_submitted = Signal(str)
    expand_requested = Signal()
    cancel_requested = Signal()
    dismissed = Signal()
    #: The mic: start talking to Mike, or finish (the full window's mic, here).
    voice_requested = Signal()
    #: An approval answered here: True, False, or "always" (for the session).
    answered = Signal(object)

    WIDTH = 360
    MARGIN = 22
    SHADOW = 16
    #: How often it's put back on top while shown: Windows lets another
    #: always-on-top window, or an app that asks for it, cover it otherwise.
    TOP_EVERY_MS = 1500

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._busy_since: float | None = None
        self._full_answer = ""
        self._drag_from: QPoint | None = None
        self._anchor: QPoint | None = self._saved_anchor()
        self._build()
        self._clock = QTimer(self)
        self._clock.setInterval(500)
        self._clock.timeout.connect(self._tick)
        self._top = QTimer(self)
        self._top.setInterval(self.TOP_EVERY_MS)
        self._top.timeout.connect(self._stay_on_top)
        self.hide()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.SHADOW, self.SHADOW, self.SHADOW, self.SHADOW)
        outer.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("cornerCard")
        # anywhere that isn't a control picks the corner up
        self._card.setCursor(Qt.OpenHandCursor)
        self._card.setToolTip("Drag to move")
        col = QVBoxLayout(self._card)
        col.setContentsMargins(14, 12, 10, 10)
        col.setSpacing(8)

        # ── the mission you're on, if there is one: one quiet line ──
        self._mission = MissionLine()
        self._mission.clicked.connect(self.expand_requested.emit)
        col.addWidget(self._mission)

        # ── what Mike is doing — only while he's doing something ──
        self._status_row = QWidget()
        srow = QHBoxLayout(self._status_row)
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(8)
        self._status = QLabel("")
        self._status.setFont(style.font(style.SMALL, QFont.Weight.Medium))
        self._status.setStyleSheet(f"color:{style.INK_SOFT};background:transparent;")
        srow.addWidget(self._status, 1)
        self._elapsed = QLabel("")
        self._elapsed.setFont(style.font(style.CAPTION))
        self._elapsed.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
        srow.addWidget(self._elapsed, 0, Qt.AlignVCenter)
        self._stop = IconButton("stop", "Stop Mike (Esc)", size=26, icon_size=16, variant="solid")
        self._stop.clicked.connect(self.cancel_requested.emit)
        srow.addWidget(self._stop, 0, Qt.AlignVCenter)
        self._status_row.hide()
        col.addWidget(self._status_row)

        # ── an approval Mike is waiting on, answered right here ──
        self._confirm = _corner_confirm()
        self._confirm.setCursor(Qt.ArrowCursor)
        self._confirm.approved.connect(lambda: self._answer_confirmation(True))
        self._confirm.denied.connect(lambda: self._answer_confirmation(False))
        self._confirm.always.connect(lambda: self._answer_confirmation("always"))
        self._confirm.hide()
        col.addWidget(self._confirm)

        # the nib drawing the voice — yours while listening, Mike's while he
        # speaks — for "Hey Mike" and the hotkey, where the corner is all
        # there is on screen
        from ui.workspace.voicetrace import VoiceTrace
        self._trace = VoiceTrace(compact=True)
        self._trace.hide()
        col.addWidget(self._trace)

        # ── what Mike said ──
        self._answer = QLabel("")
        self._answer.setWordWrap(True)
        self._answer.setTextFormat(Qt.PlainText)
        self._answer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._answer.setCursor(Qt.IBeamCursor)
        self._answer.setFont(style.font(style.BODY))
        self._answer.setStyleSheet(f"color:{style.INK};background:transparent;")
        self._answer.hide()
        col.addWidget(self._answer)

        self._more = QLabel("")
        self._more.setFont(style.font(style.CAPTION, QFont.Weight.Medium))
        self._more.setCursor(Qt.PointingHandCursor)
        self._more.setStyleSheet(f"color:{style.accent()};background:transparent;")
        self._more.setText("Read the full answer in Mike →")
        self._more.mousePressEvent = lambda _e: self.expand_requested.emit()
        self._more.hide()
        col.addWidget(self._more)

        # ── the always-there row: mark, a line to talk, the mic, open, hide ──
        row = QHBoxLayout()
        row.setSpacing(8)
        self.mark = PresenceMark(24)
        row.addWidget(self.mark, 0, Qt.AlignVCenter)

        self._field = _CornerField(self._submit)
        self._field.setPlaceholderText("Ask Mike…")
        self._field.setFont(style.font(style.BODY))
        self._field.setFrame(False)
        self._field.setCursor(Qt.IBeamCursor)
        self._field.setStyleSheet(
            f"QLineEdit{{background:transparent;border:none;color:{style.INK};"
            f"selection-background-color:{style.accent()};}}")
        row.addWidget(self._field, 1)

        self._mic = IconButton("mic", "Talk to Mike (F6)", size=28, icon_size=15)
        self._mic.clicked.connect(self.voice_requested.emit)
        row.addWidget(self._mic, 0, Qt.AlignVCenter)

        self._expand = IconButton("expand", "Open Mike", size=28, icon_size=15)
        self._expand.clicked.connect(self.expand_requested.emit)
        row.addWidget(self._expand, 0, Qt.AlignVCenter)

        # A real way to send the corner away. Mike stays in the taskbar (the
        # window is minimised, not gone), so this dismisses the companion
        # without losing Mike — the taskbar or the hotkey brings him back.
        self._close = IconButton("close", "Hide the corner — Mike stays in the taskbar",
                                 size=28, icon_size=14)
        self._close.clicked.connect(self._dismiss_clicked)
        row.addWidget(self._close, 0, Qt.AlignVCenter)
        for control in (self._mic, self._expand, self._close):
            control.setCursor(Qt.PointingHandCursor)
        col.addLayout(row)

        outer.addWidget(self._card)

        self._card.setStyleSheet(
            f"QFrame#cornerCard{{background:{style.SURFACE};"
            f"border:1px solid {style.HAIRLINE};border-radius:16px;}}")

    # ── placement ─────────────────────────────────────────
    def _default_anchor(self) -> QPoint:
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 720)
        return QPoint(geo.right() - self.MARGIN + self.SHADOW,
                      geo.bottom() - self.MARGIN + self.SHADOW)

    def _place(self) -> None:
        """Sized to what it shows, growing upward from where it was put -- by
        default the bottom-right corner -- and kept on that screen."""
        anchor = self._anchor or self._default_anchor()
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        # the height its content needs at this width -- not the card shrunk
        # to its own liking, which left it narrower than the window whenever
        # the window's size didn't change (a grey band down the side)
        w = self.WIDTH
        self.layout().activate()
        height = self.heightForWidth(w) if self.hasHeightForWidth() else self.sizeHint().height()
        x = min(max(anchor.x() - w, geo.left() - self.SHADOW), geo.right() - w + self.SHADOW)
        y = min(max(anchor.y() - height, geo.top() - self.SHADOW), geo.bottom() - height + self.SHADOW)
        self.setGeometry(QRect(x, y, w, height))

    def _resize_to_content(self) -> None:
        # tied to this widget: Qt drops it if the corner is gone by then,
        # rather than calling into a deleted window (an access violation)
        QTimer.singleShot(0, self, self._place)

    @staticmethod
    def _saved_anchor() -> QPoint | None:
        try:
            from config import preferences
            x, y = (int(v) for v in str(preferences.get(ANCHOR_PREF, "") or "").split(","))
            return QPoint(x, y)
        except Exception:
            return None

    def _remember_place(self) -> None:
        self._anchor = QPoint(self.x() + self.width(), self.y() + self.height())
        try:
            from config import preferences
            preferences.set_value(ANCHOR_PREF, f"{self._anchor.x()},{self._anchor.y()}")
        except Exception:
            pass

    # ── moved with the mouse ──────────────────────────────
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._drag_from = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._card.setCursor(Qt.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._drag_from is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_from)
            # growing mid-drag (an answer arriving) grows from here
            self._anchor = QPoint(self.x() + self.width(), self.y() + self.height())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self._drag_from is not None and e.button() == Qt.LeftButton:
            self._drag_from = None
            self._card.setCursor(Qt.OpenHandCursor)
            self._remember_place()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    # ── above everything, while it's shown ───────────────
    def _stay_on_top(self) -> None:
        """Topmost again, without taking the focus: WindowStaysOnTopHint
        alone let another always-on-top window cover it."""
        if sys.platform != "win32" or not self.isVisible():
            return
        try:
            import win32con
            import win32gui
            win32gui.SetWindowPos(int(self.winId()), win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                                  | win32con.SWP_NOACTIVATE | win32con.SWP_NOOWNERZORDER)
        except Exception:
            pass

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._stay_on_top()
        self._top.start()

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self._top.stop()

    # ── contract the controller drives ────────────────────
    def activate(self, start_listening: bool = False) -> None:
        self.clear_response()
        self._field.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self._field.setFocus()
        self._place()
        if start_listening:
            self.set_state("listening")

    def show_presence(self) -> None:
        """Come to the corner as a quiet companion (no focus stealing)."""
        self.clear_response()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._place()

    def dismiss(self) -> None:
        self._voice("idle")
        self.hide()
        self.clear_response()
        self.mark.set_state("idle")

    def _voice(self, state: str) -> None:
        listening = state == "listening"
        self._mic.set_icon("stop" if listening else "mic")
        self._mic.setToolTip("Done talking — send it (F6)" if listening else "Talk to Mike (F6)")
        self._mic.set_tint(style.INK if listening else None)
        mode = {"listening": "listen", "transcribing": "read", "speaking": "speak"}.get(state)
        if state == "speaking":
            try:
                from config import preferences
                if not preferences.get("voice_enabled", True):
                    mode = None
            except Exception:
                pass
        if mode is None:
            self._trace.set_mode("off")
            if self._trace.isVisible():
                self._trace.hide()
                self._resize_to_content()
            return
        self._trace.set_mode(mode)
        if not self._trace.isVisible():
            self._trace.show()
            self._resize_to_content()

    def set_state(self, state: str, status: str = "") -> None:
        self._voice(state)
        self.mark.set_state("listening" if state == "transcribing" else state)
        text = status or _STATE_TEXT.get(state, "")
        if text:
            self._show_status(text, busy=state in _BUSY)
        elif state == "speaking":
            self._hide_status()

    def set_mission(self, mission: dict | None, newly_done: list[str] | None = None) -> None:
        if self._mission.set_mission(mission, newly_done) and self.isVisible():
            self._resize_to_content()

    def show_tool_status(self, text: str) -> None:
        self.mark.set_state("working")
        self._show_status(text, busy=True)

    def show_tool_done(self, text: str, success: bool = True) -> None:
        pass

    def ask(self, description: str, offer: str = "") -> None:
        """Mike is waiting for an OK: asked here, where the student is --
        not only in a workspace that's minimised."""
        self._hide_status()
        self.mark.set_state("idle")
        self._confirm.ask(description, offer)
        self._confirm.show()
        self._resize_to_content()
        self._stay_on_top()

    def hide_confirmation(self) -> None:
        if self._confirm.isVisible():
            self._confirm.hide()
            self._resize_to_content()

    def set_response(self, text: str) -> None:
        self._full_answer = text
        self._hide_status()
        self._render_answer()

    def append_response(self, token: str) -> None:
        if self._status_row.isVisible():
            # the answer arriving is the end of "working on it"
            self._hide_status()
        self._full_answer += token
        self._render_answer()

    def clear_response(self) -> None:
        self._full_answer = ""
        self._answer.setText("")
        self._answer.hide()
        self._more.hide()
        self._hide_status()
        self._resize_to_content()

    def finish(self) -> None:
        self.mark.set_state("idle")
        self._voice("idle")
        self._hide_status()

    def voice_stopped(self) -> None:
        """The mic has closed: the button offers to talk again."""
        self._voice("idle")

    # ── internals ─────────────────────────────────────────
    def _answer_confirmation(self, decision) -> None:
        self.hide_confirmation()
        self.answered.emit(decision)

    def _render_answer(self) -> None:
        text = self._full_answer.strip()
        if not text:
            self._answer.hide()
            self._more.hide()
            return
        long = len(text) > ANSWER_CHARS
        if long:
            cut = text[:ANSWER_CHARS].rsplit(" ", 1)[0].rstrip(",.;: ")
            text = cut + "…"
        self._answer.setText(text)
        self._answer.show()
        self._more.setVisible(long)
        self._resize_to_content()

    def _show_status(self, text: str, busy: bool) -> None:
        self._status.setText(" ".join(text.split())[:70])
        self._stop.setVisible(busy and not text.startswith("Listening"))
        if busy and self._busy_since is None:
            self._busy_since = time.monotonic()
        if not busy:
            self._busy_since = None
        self._tick()
        if busy:
            self._clock.start()
        self._status_row.show()
        self._resize_to_content()

    def _hide_status(self) -> None:
        self._busy_since = None
        self._clock.stop()
        self._elapsed.setText("")
        if self._status_row.isVisible():
            self._status_row.hide()
            self._resize_to_content()

    def _tick(self) -> None:
        if self._busy_since is None:
            self._elapsed.setText("")
            return
        secs = int(time.monotonic() - self._busy_since)
        self._elapsed.setText(f"{secs}s" if secs >= 2 else "")

    def _dismiss_clicked(self) -> None:
        self.dismiss()
        self.dismissed.emit()

    def _submit(self) -> None:
        text = self._field.text().strip()
        if text:
            self._field.clear()
            self.message_submitted.emit(text)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.cancel_requested.emit()
            self.dismiss()
            return
        super().keyPressEvent(event)

    # ── the floating material: a soft shadowed card ───────
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        m = self.SHADOW
        radius = 16.0
        bx, by = m, m
        bw, bh = self.width() - 2 * m, self.height() - 2 * m
        for i in range(m, 0, -2):
            a = int(3 + 34 * (1 - i / m) ** 2.2)
            sh = QPainterPath()
            sh.addRoundedRect(bx - i, by - i + 4, bw + 2 * i, bh + 2 * i,
                              radius + i, radius + i)
            p.fillPath(sh, QColor(0, 0, 0, a))
