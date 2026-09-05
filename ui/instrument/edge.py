"""D1 — the edge. Mike, glanceable, at the side of the screen.

A small brass-and-glass instrument window that opens from the screen edge
when there's something worth a glance, and collapses to a resting dial the
size of a rivet when there isn't. Never takes focus.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ui.home import motion
from ui.instrument import tokens
from ui.instrument.dial import Dial
from ui.instrument.widgets import EngravedLabel, InkFact


class EdgeStrip(QWidget):

    expand_requested = Signal()

    STRIP_W = 320
    TICK_D = 20
    LINGER_MS = 6500

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._open = False
        self._build()

        self._linger = QTimer(self)
        self._linger.setSingleShot(True)
        self._linger.timeout.connect(self.dismiss)

        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(1 if motion.reduced_motion() else 190)
        self._anim.setEasingCurve(QEasingCurve.OutBack)

        self._collapse(animate=False)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._shell = QFrame()
        self._shell.setObjectName("strip")
        self._shell.setStyleSheet(
            f"""
            QFrame#strip {{
                background: {tokens.GROUND};
                border-left: 1px solid {tokens.HAIRLINE};
                border-top: 1px solid {tokens.HAIRLINE};
                border-bottom: 1px solid {tokens.HAIRLINE};
            }}
            """
        )
        row = QHBoxLayout(self._shell)
        row.setContentsMargins(14, 12, 15, 12)
        row.setSpacing(12)

        self.dial = Dial(30)
        row.addWidget(self.dial, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(3)
        self._did = InkFact("")
        self._did.hide()
        col.addWidget(self._did)
        self._said = EngravedLabel("", colour=tokens.TEXT, size=12.5)
        self._said.setWordWrap(True)
        self._said.hide()
        col.addWidget(self._said)
        row.addLayout(col, 1)

        root.addWidget(self._shell)

        self._tick = Dial(self.TICK_D)
        self._tick.setParent(self)

    def _anchor(self) -> tuple[int, int]:
        screen = QApplication.primaryScreen()
        if screen is None:
            return 0, 0
        geo = screen.availableGeometry()
        return geo.right() + 1, geo.top() + int(geo.height() * 0.24)

    def _target_height(self) -> int:
        self._shell.adjustSize()
        return max(48, self._shell.sizeHint().height())

    def _collapse(self, animate: bool = True) -> None:
        right, top = self._anchor()
        rect = QRect(right - self.TICK_D, top + 10, self.TICK_D, self.TICK_D)
        self._open = False
        self._shell.hide()
        self._tick.show()
        self._tick.setGeometry(0, 0, self.TICK_D, self.TICK_D)
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
            self.setGeometry(QRect(right - self.TICK_D, top, self.TICK_D, height))
            self.show()

        if self._open:
            self.setGeometry(rect)
            return
        self._open = True
        if motion.reduced_motion():
            self.setGeometry(rect)
            return
        self._anim.stop()
        self._anim.setStartValue(QRect(right - self.TICK_D, rect.top(), self.TICK_D, height))
        self._anim.setEndValue(rect)
        self._anim.start()

    def show_state(self, state: str, text: str = "") -> None:
        self.dial.set_state(state)
        message = " ".join((text or "").split())
        if not message:
            self.dismiss()
            return
        self._said.hide()
        self._did.show()
        self._did.set_text(self._trim(message, 84))
        self._expand()
        self._linger.stop()
        if state == "error":
            self._linger.start(self.LINGER_MS)

    def show_message(self, text: str) -> None:
        message = " ".join(text.split())
        if not message:
            return
        self._did.hide()
        self._said.show()
        self._said.set_text(self._trim(message, 130))
        self.dial.set_state("done")
        self._expand()
        self._linger.stop()
        self._linger.start(self.LINGER_MS)

    def dismiss(self) -> None:
        self._linger.stop()
        self._collapse()

    def sleep(self) -> None:
        self._linger.stop()
        self.hide()

    def wake(self) -> None:
        if not self.isVisible():
            self._collapse(animate=False)

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.expand_requested.emit()
            event.accept()
