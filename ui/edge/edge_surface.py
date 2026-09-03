"""The edge surface — Mike replying without taking over.

Depth 1 of the invocation ladder: a slim strip at the screen edge that shows
what Mike is doing and short answers, without stealing focus or covering the
work in front of the user. Never accepts keyboard focus; clicking it opens the
fuller surface.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.home import motion
from ui.theme import colors

STATE_TONE = {
    "idle": colors.HOME_ACCENT,
    "listening": colors.HOME_LIVE,
    "thinking": colors.HOME_ACCENT,
    "working": colors.HOME_LIVE,
    "needs_user": colors.HOME_ATTENTION,
    "responding": colors.HOME_ACCENT,
    "error": colors.HOME_ERROR,
    "done": colors.HOME_SUCCESS,
}

STATE_WORD = {
    "listening": "Listening",
    "thinking": "Thinking",
    "working": "Working",
    "needs_user": "Needs you",
    "error": "Problem",
}


class EdgeSurface(QWidget):
    """A glanceable strip. Shows itself when there's something to say."""

    expand_requested = Signal()

    WIDTH = 340
    HEIGHT = 52
    MARGIN = 18
    LINGER_MS = 7000

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
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._state = "idle"
        self._build()
        self._position()

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.dismiss)

        self._fade = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fade)
        self._fade.setOpacity(0.0)
        self._anim = QPropertyAnimation(self._fade, b"opacity", self)
        self._anim.setDuration(1 if motion.reduced_motion() else 180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hide_on_fade = False

    # ── Build ────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._shell = QFrame()
        self._shell.setObjectName("edge")

        row = QHBoxLayout(self._shell)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(11)

        self._dot = QLabel("●")
        self._dot.setObjectName("edge_dot")
        self._dot.setFixedWidth(10)
        row.addWidget(self._dot)

        self._text = QLabel("")
        self._text.setObjectName("edge_text")
        self._text.setTextFormat(Qt.PlainText)
        row.addWidget(self._text, 1)

        root.addWidget(self._shell)
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#edge {{
                background: rgba(12, 14, 19, 0.94);
                border: 1px solid {colors.HOME_BORDER};
                border-radius: 14px;
            }}
            QLabel#edge_text {{
                color: {colors.HOME_TEXT};
                font-size: 13px;
                background: transparent;
                border: none;
            }}
            """
        )
        self._tint(self._state)

    def _tint(self, state: str) -> None:
        tone = STATE_TONE.get(state, colors.HOME_ACCENT)
        self._dot.setStyleSheet(
            f"color: {tone}; font-size: 10px; background: transparent; border: none;"
        )

    def _position(self) -> None:
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        self.move(
            geo.right() - self.WIDTH - self.MARGIN,
            geo.top() + self.MARGIN,
        )

    # ── API ──────────────────────────────────────────────────

    def show_state(self, state: str, text: str = "") -> None:
        """Reflect a real state. Transient states linger, idle retreats."""

        self._state = state
        self._tint(state)

        message = text or STATE_WORD.get(state, "")

        if not message:
            self.dismiss()
            return

        self._text.setText(self._trim(message))
        self._reveal()

        # A state that resolves on its own gets a linger; one that needs the
        # user stays until it's dealt with.
        self._hide_timer.stop()
        if state in ("done", "responding", "error"):
            self._hide_timer.start(self.LINGER_MS)

    def show_message(self, text: str) -> None:
        if not text.strip():
            return
        self._text.setText(self._trim(text))
        self._tint("done")
        self._reveal()
        self._hide_timer.start(self.LINGER_MS)

    @staticmethod
    def _trim(text: str) -> str:
        flat = " ".join(text.split())
        return flat if len(flat) <= 68 else flat[:67] + "…"

    def _reveal(self) -> None:
        self._position()
        if not self.isVisible():
            self.show()
        self._anim.stop()
        self._anim.setStartValue(self._fade.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()

    def dismiss(self) -> None:
        self._hide_timer.stop()
        if not self.isVisible():
            return
        self._anim.stop()
        self._anim.setStartValue(self._fade.opacity())
        self._anim.setEndValue(0.0)
        if not self._hide_on_fade:
            # Connected once; disconnecting each time makes PySide complain
            # when there was nothing attached.
            self._anim.finished.connect(self._hide_if_faded)
            self._hide_on_fade = True
        self._anim.start()

    def _hide_if_faded(self) -> None:
        if self._fade.opacity() <= 0.01:
            self.hide()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.expand_requested.emit()
            event.accept()
