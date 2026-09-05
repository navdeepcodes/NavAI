"""Mike's floating assistant window — compact, always-on-top interaction surface."""
from __future__ import annotations

from PySide6.QtCore import (
    Qt, Signal, QPoint, QTimer, )
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QFrame, QSizePolicy, QApplication,
)

from ui.theme import colors, typography
from ui.widgets.floating.presence import PresenceIndicator


class FloatingInput(QTextEdit):
    """Single-line text input that submits on Enter."""

    submitted = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Ask Mike anything...")
        self.setAcceptRichText(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(36)
        self.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                border: none;
                color: {colors.TEXT};
                font-size: {typography.BODY}px;
                padding: 6px 0px;
            }}
        """)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            text = self.toPlainText().strip()
            if text:
                self.submitted.emit(text)
                self.clear()
            return
        if event.key() == Qt.Key_Escape:
            self.window().dismiss()
            return
        super().keyPressEvent(event)


class FloatingWindow(QWidget):
    """Compact floating assistant that appears on activation."""

    message_submitted = Signal(str)
    expand_requested = Signal()
    cancel_requested = Signal()

    WIDTH = 380
    COLLAPSED_HEIGHT = 160
    EXPANDED_HEIGHT = 280

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)

        self._drag_pos: QPoint | None = None
        self._state = "idle"
        self._status_text = ""
        self._response_lines: list[str] = []
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.dismiss)

        self._build_ui()
        self._position_on_screen()

    def _build_ui(self) -> None:
        self.setFixedWidth(self.WIDTH)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        self._container = QFrame(self)
        self._container.setObjectName("float_container")

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Top row: presence + title + expand button
        top = QHBoxLayout()
        top.setSpacing(10)

        self._presence = PresenceIndicator(self._container)
        top.addWidget(self._presence)

        self._title = QLabel("Mike")
        self._title.setObjectName("float_title")
        top.addWidget(self._title)

        top.addStretch()

        self._expand_btn = QPushButton("⬒")
        self._expand_btn.setObjectName("float_expand")
        self._expand_btn.setFixedSize(28, 28)
        self._expand_btn.setToolTip("Open full window")
        self._expand_btn.clicked.connect(self.expand_requested.emit)
        top.addWidget(self._expand_btn)

        layout.addLayout(top)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setObjectName("float_status")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Response area
        self._response = QLabel("")
        self._response.setObjectName("float_response")
        self._response.setWordWrap(True)
        self._response.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._response.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._response.setMinimumHeight(0)
        self._response.hide()
        layout.addWidget(self._response, 1)

        layout.addStretch()

        # Input row
        input_frame = QFrame()
        input_frame.setObjectName("float_input_frame")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 4, 8, 4)
        input_layout.setSpacing(8)

        self._input = FloatingInput(input_frame)
        self._input.submitted.connect(self._on_submit)
        input_layout.addWidget(self._input, 1)

        self._send = QPushButton("↑")
        self._send.setObjectName("float_send")
        self._send.setFixedSize(28, 28)
        self._send.clicked.connect(self._submit)
        input_layout.addWidget(self._send)

        layout.addWidget(input_frame)

        root.addWidget(self._container)
        self._apply_theme()
        self.setFixedHeight(self.COLLAPSED_HEIGHT)

    def _apply_theme(self) -> None:
        self._container.setStyleSheet(f"""
            QFrame#float_container {{
                background: rgba(18, 18, 24, 0.92);
                border: 1px solid rgba(60, 65, 90, 0.4);
                border-radius: 16px;
            }}
            QLabel#float_title {{
                color: {colors.TEXT};
                font-size: 16px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QLabel#float_status {{
                color: {colors.TEXT_SECONDARY};
                font-size: {typography.SMALL}px;
                background: transparent;
                border: none;
                padding-left: 2px;
            }}
            QLabel#float_response {{
                color: {colors.TEXT};
                font-size: {typography.SMALL}px;
                background: transparent;
                border: none;
                padding: 0 2px;
            }}
            QPushButton#float_expand {{
                background: transparent;
                border: none;
                border-radius: 14px;
                color: {colors.TEXT_MUTED};
                font-size: 14px;
            }}
            QPushButton#float_expand:hover {{
                background: rgba(255, 255, 255, 0.06);
                color: {colors.TEXT};
            }}
            QFrame#float_input_frame {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 12px;
            }}
            QPushButton#float_send {{
                background: {colors.ACCENT};
                border: none;
                border-radius: 14px;
                color: #fff;
                font-size: 14px;
                font-weight: 700;
            }}
            QPushButton#float_send:hover {{
                background: {colors.ACCENT_DIM};
            }}
        """)

    def _position_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.WIDTH - 24
            y = geo.top() + 80
            self.move(x, y)

    # ── State API ────────────────────────────────────────────

    def set_state(self, state: str, status: str = "") -> None:
        self._state = state
        self._dismiss_timer.stop()

        self._presence.set_state(state)

        status_map = {
            "idle": "",
            "listening": "Listening...",
            "transcribing": "Transcribing...",
            "thinking": "Thinking...",
            "speaking": "",
            "done": "",
        }

        display = status or status_map.get(state, "")
        self._status_label.setText(display)

        if state == "idle":
            self._status_label.setText("")

    def show_tool_status(self, text: str) -> None:
        self._presence.set_state("tool")
        self._status_label.setText(text)

    def show_tool_done(self, text: str, success: bool = True) -> None:
        mark = "✓" if success else "✗"
        self._status_label.setText(f"{mark} {text}")

    def set_response(self, text: str) -> None:
        if not text.strip():
            return
        lines = text.strip().split("\n")
        display = "\n".join(lines[:6])
        if len(lines) > 6:
            display += "\n..."
        self._response.setText(display)
        self._response.show()
        if self.height() < self.EXPANDED_HEIGHT:
            self.setFixedHeight(self.EXPANDED_HEIGHT)

    def append_response(self, token: str) -> None:
        current = self._response.text()
        current += token
        lines = current.split("\n")
        if len(lines) > 6:
            current = "\n".join(lines[:6]) + "\n..."
        self._response.setText(current)
        if not self._response.isVisible():
            self._response.show()
            if self.height() < self.EXPANDED_HEIGHT:
                self.setFixedHeight(self.EXPANDED_HEIGHT)

    def clear_response(self) -> None:
        self._response.setText("")
        self._response.hide()
        self.setFixedHeight(self.COLLAPSED_HEIGHT)

    def finish(self) -> None:
        self._presence.set_state("done")
        self._status_label.setText("")
        self._dismiss_timer.start(8000)

    # ── Activation ────────────────────────────────────────────

    def activate(self, start_listening: bool = False) -> None:
        self._dismiss_timer.stop()
        self.clear_response()
        self.set_state("idle")
        self.show()
        self.raise_()
        if start_listening:
            self.set_state("listening")
        else:
            self._input.setFocus(Qt.OtherFocusReason)

    def dismiss(self) -> None:
        if self._state in ("listening", "transcribing", "thinking", "tool", "speaking"):
            self.cancel_requested.emit()

        self._dismiss_timer.stop()
        self.hide()
        self.clear_response()
        self.set_state("idle")

    # ── Input ──────────────────────────────────────────────

    def _on_submit(self, text: str) -> None:
        self.message_submitted.emit(text)

    def _submit(self) -> None:
        text = self._input.toPlainText().strip()
        if text:
            self.message_submitted.emit(text)
            self._input.clear()

    # ── Dragging ──────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.dismiss()
            return
        if event.key() == Qt.Key_CapsLock:
            # Bubble up to parent handling
            if self.parent():
                QApplication.sendEvent(self.parent(), event)
            return
        super().keyPressEvent(event)
