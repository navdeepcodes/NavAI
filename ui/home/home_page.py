"""Mike's Home.

A centred, state-driven surface rather than a scrolling transcript. Mike's
presence is the constant; everything else appears only while it's relevant.

Implements the same method contract UIController already calls on ChatPage, so
the controller keeps driving it with real runtime signals.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedLayout,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ui.home.activity_panel import ActivityPanel
from ui.home.capabilities import CapabilitiesOverlay
from ui.home.confirm_panel import ConfirmPanel
from ui.home.context_strip import ContextStrip
from ui.home.presence_core import PresenceCore
from ui.home.settings_panel import SettingsPanel
from ui.theme import colors
from ui.widgets.conversation import ConversationPanel
from ui.widgets.input import InputBar


class _DualCard:
    """
    Handle for one tool step. Keeps the Home's activity row and the history
    transcript's tool bubble in sync, and exposes the small surface the
    controller expects (`_label`, `mark_done`).
    """

    def __init__(self, step, bubble) -> None:
        self._step = step
        self._bubble = bubble

    @property
    def _label(self):
        return self._step._label

    def mark_done(self, success: bool = True) -> None:
        self._step.mark_done(success)
        if self._bubble is not None:
            self._bubble.mark_done(success=success)


class _ResponseStream:
    """Streams tokens into the Home's response area and the transcript at once."""

    def __init__(self, page: "HomePage", bubble) -> None:
        self._page = page
        self._bubble = bubble

    def append_text(self, text: str) -> None:
        self._page._append_response(text)
        if self._bubble is not None:
            self._bubble.append_text(text)


class HomePage(QWidget):

    STAGE_WIDTH = 620

    def __init__(self, settings_hooks: dict | None = None) -> None:
        super().__init__()

        self._state = "idle"
        self._response_text = ""
        self._settings_hooks = settings_hooks or {}

        self._build()
        self._apply_theme()
        self.set_state("idle")

    # ── Construction ─────────────────────────────────────────

    def _build(self) -> None:
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setStackingMode(QStackedLayout.StackOne)

        self._stack.addWidget(self._build_stage())

        self.capabilities = CapabilitiesOverlay()
        self.capabilities.dismissed.connect(self.hide_capabilities)
        self._stack.addWidget(self.capabilities)

        # Real transcript. Hidden by default — the Home is not a chat log —
        # but fully populated so history is genuine when opened.
        self.conversation = ConversationPanel()
        self._stack.addWidget(self.conversation)

        self.settings = SettingsPanel(self._settings_hooks)
        self.settings.dismissed.connect(self.close_overlays)
        self._stack.addWidget(self.settings)

    def _build_stage(self) -> QWidget:
        stage = QWidget()
        stage.setObjectName("stage")

        root = QVBoxLayout(stage)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.context = ContextStrip()
        root.addWidget(self.context)

        # Presence, what Mike is saying, and the composer travel together as a
        # single centred cluster. Pinning the composer to the bottom instead
        # leaves it stranded from the content in a tall window.
        cluster = QWidget()
        column = QVBoxLayout(cluster)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        # Layer 1 — presence
        self.presence = PresenceCore(size=210)
        column.addWidget(self.presence, 0, Qt.AlignHCenter)

        column.addSpacing(26)

        # Layer 2 — current interaction
        self._headline = QLabel()
        self._headline.setObjectName("headline")
        self._headline.setAlignment(Qt.AlignCenter)
        self._headline.setWordWrap(True)
        column.addWidget(self._headline)

        self._subline = QLabel()
        self._subline.setObjectName("subline")
        self._subline.setAlignment(Qt.AlignCenter)
        self._subline.setWordWrap(True)
        column.addWidget(self._subline)

        column.addWidget(self._build_response(), 0, Qt.AlignHCenter)

        # Layer 3 — activity
        self.activity = ActivityPanel()
        self.activity.hide()
        column.addWidget(self.activity, 0, Qt.AlignHCenter)

        # Needs-user
        self.confirm = ConfirmPanel()
        self.confirm.hide()
        column.addWidget(self.confirm, 0, Qt.AlignHCenter)

        column.addSpacing(30)
        column.addWidget(self._build_composer(), 0, Qt.AlignHCenter)

        root.addStretch(1)
        root.addWidget(cluster, 0, Qt.AlignHCenter)
        root.addStretch(1)

        root.addWidget(self._build_links(), 0, Qt.AlignHCenter)

        return stage

    def _build_response(self) -> QWidget:
        # A wrapped QLabel inside a QScrollArea reports the wrong height and
        # clips its own first line, so the response is a read-only text view —
        # which also makes the answer selectable.
        self._response = QTextBrowser()
        self._response.setObjectName("response")
        self._response.setFrameShape(QFrame.NoFrame)
        self._response.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._response.setFixedWidth(self.STAGE_WIDTH)
        self._response.setOpenExternalLinks(False)
        self._response.hide()

        return self._response

    MIN_RESPONSE_HEIGHT = 34
    MAX_RESPONSE_HEIGHT = 220

    def _fit_response(self) -> None:
        doc = self._response.document()

        # A one-line answer left-aligned in a wide box reads as misaligned
        # against the centred presence above it; a paragraph does not.
        text = self._response_text.strip()
        short = len(text) < 90 and "\n" not in text

        option = QTextOption(Qt.AlignCenter if short else Qt.AlignLeft)
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(option)

        doc.setTextWidth(self.STAGE_WIDTH - 16)
        height = int(doc.size().height()) + 12
        self._response.setFixedHeight(
            max(self.MIN_RESPONSE_HEIGHT, min(self.MAX_RESPONSE_HEIGHT, height))
        )

    def _build_composer(self) -> QWidget:
        self.input = InputBar()
        self.input.setFixedWidth(self.STAGE_WIDTH)
        return self.input

    def _build_links(self) -> QWidget:
        footer = QWidget()
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 18)
        layout.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(18)
        controls.addStretch()

        self._capabilities_btn = QPushButton("Capabilities")
        self._capabilities_btn.setObjectName("ghost_btn")
        self._capabilities_btn.setCursor(Qt.PointingHandCursor)
        self._capabilities_btn.clicked.connect(self.show_capabilities)
        controls.addWidget(self._capabilities_btn)

        self._settings_btn = QPushButton("Settings")
        self._settings_btn.setObjectName("ghost_btn")
        self._settings_btn.setCursor(Qt.PointingHandCursor)
        self._settings_btn.clicked.connect(self.show_settings)
        controls.addWidget(self._settings_btn)

        self._history_btn = QPushButton("History")
        self._history_btn.setObjectName("ghost_btn")
        self._history_btn.setCursor(Qt.PointingHandCursor)
        self._history_btn.clicked.connect(self.toggle_history)
        controls.addWidget(self._history_btn)

        controls.addStretch()
        layout.addLayout(controls)

        return footer

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget#stage {{
                background: {colors.HOME_GROUND};
            }}
            QLabel#headline {{
                color: {colors.HOME_TEXT};
                font-size: 25px;
                font-weight: 300;
                letter-spacing: -0.3px;
                background: transparent;
                border: none;
            }}
            QLabel#subline {{
                color: {colors.HOME_TEXT_MUTED};
                font-size: 14px;
                background: transparent;
                border: none;
                padding-top: 6px;
            }}
            QTextBrowser#response {{
                color: {colors.HOME_TEXT};
                font-size: 15px;
                background: transparent;
                border: none;
                padding: 0 6px;
                selection-background-color: {colors.HOME_ACCENT_DEEP};
            }}
            QPushButton#ghost_btn {{
                background: transparent;
                border: none;
                color: {colors.HOME_TEXT_MUTED};
                font-size: 12px;
                padding: 4px 8px;
            }}
            QPushButton#ghost_btn:hover {{
                color: {colors.HOME_TEXT_SECONDARY};
            }}
            """
        )

        # The composer is shared with the old chat surface, so it gets the
        # Home palette applied over the top rather than being forked.
        self.input.setStyleSheet(
            f"""
            InputBar {{
                background: transparent;
                border: none;
            }}
            QFrame#composer {{
                background: {colors.HOME_SURFACE};
                border: 1px solid {colors.HOME_BORDER};
                border-radius: 20px;
            }}
            QTextEdit {{
                background: transparent;
                border: none;
                color: {colors.HOME_TEXT};
                font-size: 14px;
                padding: 4px 2px;
            }}
            QPushButton#send_btn {{
                background: {colors.HOME_ACCENT};
                border: none;
                border-radius: 16px;
                color: #06080F;
                font-size: 15px;
                font-weight: 700;
            }}
            QPushButton#send_btn:hover {{
                background: {colors.HOME_LIVE};
            }}
            QPushButton#send_btn:disabled {{
                background: {colors.HOME_SURFACE_RAISED};
                color: {colors.HOME_TEXT_MUTED};
            }}
            QLabel#hint {{
                color: {colors.HOME_TEXT_MUTED};
                font-size: 11px;
                background: transparent;
                border: none;
            }}
            """
        )
        self.input.hide_hint()

    # ── State machine ────────────────────────────────────────

    def set_state(self, state: str) -> None:
        self._state = state
        self.presence.set_state(state)

        self.activity.setVisible(state == "working")
        self.confirm.setVisible(state == "needs_user")

        if state == "idle":
            # A finished answer stays on screen — the greeting only returns
            # once there's nothing left to read.
            resting = not self._response_text.strip()
            if resting:
                self._headline.setText(self._greeting())
                self._subline.setText("Ready when you are.")
            self._headline.setVisible(resting)
            self._subline.setVisible(resting)
            self.context.set_available(True)

        elif state == "listening":
            self._headline.setText("Listening")
            self._subline.setText("")
            self._headline.show()
            self._subline.hide()

        elif state == "thinking":
            self._headline.setText("Thinking")
            self._subline.setText("")
            self._headline.show()
            self._subline.hide()

        elif state == "working":
            self._headline.hide()
            self._subline.hide()

        elif state == "needs_user":
            self._headline.hide()
            self._subline.hide()

        elif state in ("responding", "error", "done"):
            self._headline.hide()
            self._subline.hide()

    def state(self) -> str:
        return self._state

    def _greeting(self) -> str:
        hour = datetime.now().hour
        if hour < 12:
            return "Good morning."
        if hour < 17:
            return "Good afternoon."
        return "Good evening."

    # ── Controller contract ──────────────────────────────────

    def add_user_message(self, text: str) -> None:
        self.conversation.add_user(text)
        self._clear_response()
        self.activity.reset()

    def add_mike_message(self, text: str) -> None:
        self.conversation.add_mike(text)
        self._set_response(text)

    def begin_mike_stream(self):
        bubble = self.conversation.begin_mike_stream()
        self._clear_response()
        self.set_state("responding")
        return _ResponseStream(self, bubble)

    def add_action_card(self, text: str):
        if self._state != "working":
            self.set_state("working")

        step = self.activity.begin_step(text)
        bubble = self.conversation.add_action_card(text)
        return _DualCard(step, bubble)

    def show_tool_status(self, text: str) -> None:
        self.conversation.show_tool(text)

    def show_thinking(self) -> None:
        if self._state not in ("working", "needs_user"):
            self.set_state("thinking")

    def hide_thinking(self) -> None:
        pass

    def clear(self) -> None:
        self.conversation.clear()
        self.activity.reset()
        self._clear_response()
        self.set_state("idle")

    # ── Response area ────────────────────────────────────────

    def _set_response(self, text: str) -> None:
        self._response_text = text
        self._response.setPlainText(text)
        self._response.setVisible(bool(text.strip()))
        self._fit_response()
        self._scroll_response_to_bottom()

    def _append_response(self, text: str) -> None:
        self._response_text += text
        self._response.setPlainText(self._response_text)
        self._response.show()
        self._fit_response()
        self._scroll_response_to_bottom()

    def _clear_response(self) -> None:
        self._response_text = ""
        self._response.setPlainText("")
        self._response.hide()

    def _scroll_response_to_bottom(self) -> None:
        bar = self._response.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ── Overlays ─────────────────────────────────────────────

    def show_capabilities(self) -> None:
        self._stack.setCurrentWidget(self.capabilities)
        self.capabilities.setFocus(Qt.OtherFocusReason)

    def hide_capabilities(self) -> None:
        self._stack.setCurrentIndex(0)
        self.input.focus()

    def show_settings(self) -> None:
        self.settings.refresh()
        self._stack.setCurrentWidget(self.settings)
        self.settings.setFocus(Qt.OtherFocusReason)

    def toggle_history(self) -> None:
        if self._stack.currentWidget() is self.conversation:
            self._stack.setCurrentIndex(0)
            self._history_btn.setText("History")
            self.input.focus()
        else:
            self._stack.setCurrentWidget(self.conversation)
            self._history_btn.setText("Back")
            self.conversation.scroll_to_bottom()

    def showing_overlay(self) -> bool:
        return self._stack.currentIndex() != 0

    def close_overlays(self) -> None:
        self._stack.setCurrentIndex(0)
        self._history_btn.setText("History")
        self.input.focus()
