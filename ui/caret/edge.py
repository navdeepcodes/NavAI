"""D1 — the edge. The primary surface.

A temporary opening at the side of the screen. It never takes focus, never
covers more than a corner of the user's work, and collapses back to a 3px
tick when there is nothing to say. Everything the user does stays in front.

Geometry is borrowed from the SEAM study: the strip grows leftward along one
axis from the screen edge, flush and hard-edged, as though the display made
room rather than a panel flew in.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ui.caret import tokens
from ui.caret.caret import Caret
from ui.caret.text import Machine, Prose
from ui.home import motion


class EdgeStrip(QWidget):
    """Mike, at the edge of what you're doing."""

    expand_requested = Signal()

    STRIP_W = 344
    TICK_W = 3
    TICK_H = 22
    LINGER_MS = 6500

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._open = False
        self._state = "idle"

        self._build()

        self._linger = QTimer(self)
        self._linger.setSingleShot(True)
        self._linger.timeout.connect(self.dismiss)

        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(1 if motion.reduced_motion() else 170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._collapse(animate=False)

    # ── Build ────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._shell = QFrame()
        self._shell.setObjectName("strip")
        self._shell.setStyleSheet(
            f"""
            QFrame#strip {{
                background: {tokens.GROUND};
                border: none;
                border-left: 1px solid {tokens.HAIRLINE};
                border-top: 1px solid {tokens.HAIRLINE};
                border-bottom: 1px solid {tokens.HAIRLINE};
            }}
            """
        )

        row = QHBoxLayout(self._shell)
        row.setContentsMargins(15, 11, 16, 12)
        row.setSpacing(11)

        self.caret = Caret(tokens.CARET_W, 13)
        row.addWidget(self.caret, 0, Qt.AlignTop)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(5)

        self._said = Prose("", size=13)
        self._said.hide()
        column.addWidget(self._said)

        # Machine register keeps its rule here as well, so a fact looks like
        # a fact at every depth.
        self._did_rule = QFrame()
        self._did_rule.setStyleSheet(
            f"border: none; border-left: 1px solid {tokens.HAIRLINE_LIT};"
        )
        did_box = QVBoxLayout(self._did_rule)
        did_box.setContentsMargins(11, 0, 0, 0)
        self._did = Machine("", size=11)
        did_box.addWidget(self._did)
        self._did_rule.hide()
        column.addWidget(self._did_rule)

        row.addLayout(column, 1)
        root.addWidget(self._shell)

        # The tick: what "Mike is on" looks like when there is nothing to say.
        self._tick = Caret(self.TICK_W, self.TICK_H)
        self._tick.setParent(self)

    # ── Geometry ─────────────────────────────────────────

    def _anchor(self) -> tuple[int, int]:
        screen = QApplication.primaryScreen()
        if screen is None:
            return 0, 0
        geo = screen.availableGeometry()
        return geo.right() + 1, geo.top() + int(geo.height() * 0.26)

    def _target_height(self) -> int:
        self._shell.adjustSize()
        return max(44, self._shell.sizeHint().height())

    def _collapse(self, animate: bool = True) -> None:
        right, top = self._anchor()
        rect = QRect(
            right - self.TICK_W,
            top + 14,
            self.TICK_W,
            self.TICK_H,
        )
        self._open = False
        self._shell.hide()
        self._tick.show()
        self._tick.setGeometry(0, 0, self.TICK_W, self.TICK_H)
        self._tick.set_state("idle")

        if animate and self.isVisible() and not motion.reduced_motion():
            self._anim.stop()
            self._anim.setStartValue(self.geometry())
            self._anim.setEndValue(rect)
            self._anim.start()
        else:
            self.setGeometry(rect)

        if not self.isVisible():
            self.show()

    def _expand(self) -> None:
        right, top = self._anchor()
        height = self._target_height()
        rect = QRect(right - self.STRIP_W, top, self.STRIP_W, height)

        self._tick.hide()
        self._shell.show()

        if not self.isVisible():
            self.setGeometry(QRect(right - self.TICK_W, top, self.TICK_W, height))
            self.show()

        if self._open:
            self.setGeometry(rect)
            return

        self._open = True
        if motion.reduced_motion():
            self.setGeometry(rect)
            return

        self._anim.stop()
        self._anim.setStartValue(
            QRect(right - self.TICK_W, rect.top(), self.TICK_W, height)
        )
        self._anim.setEndValue(rect)
        self._anim.start()

    # ── API the controller calls ─────────────────────────

    def show_state(self, state: str, text: str = "") -> None:
        """Reflects a real runtime state. Machine register — this is doing."""

        self._state = state
        self.caret.set_state(state)

        message = " ".join((text or "").split())
        if not message:
            self.dismiss()
            return

        self._said.hide()
        self._did_rule.show()
        self._did.set_colour(
            tokens.TEXT if state == "needs_user"
            else tokens.RED if state == "error"
            else tokens.DIM
        )
        self._did.set_text(self._trim(message, 92))
        self._expand()

        self._linger.stop()
        if state == "error":
            self._linger.start(self.LINGER_MS)

    def show_message(self, text: str) -> None:
        """Mike's own words. Prose register — this is saying."""

        message = " ".join(text.split())
        if not message:
            return

        self._did_rule.hide()
        self._said.show()
        self._said.set_text(self._trim(message, 150))
        self.caret.set_state("idle")
        self._expand()

        self._linger.stop()
        self._linger.start(self.LINGER_MS)

    def dismiss(self) -> None:
        self._linger.stop()
        self._collapse()

    # ── Ambient presence ─────────────────────────────────

    def sleep(self) -> None:
        """Home is up and Mike is already visible there — no tick needed."""
        self._linger.stop()
        self.hide()

    def wake(self) -> None:
        """Back to ambient: the 3px tick that means Mike is on."""
        if not self.isVisible():
            self._collapse(animate=False)

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.expand_requested.emit()
            event.accept()
