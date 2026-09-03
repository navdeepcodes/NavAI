"""Faces for the engines that already run.

Memory, voice, wake word and the safety gates are all live systems the user
currently cannot see or adjust. Nothing here implements behaviour — each panel
reads and edits the real engine underneath it.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from brain import activity_store, memory_store
from brain.core_tools import _CONFIRM_ACTIONS
from config import preferences
from ui.theme import colors, typography


class Toggle(QPushButton):
    """A switch bound to one preference key."""

    def __init__(self, key: str, label: str, on_change=None) -> None:
        super().__init__()
        self._key = key
        self._label = label
        self._on_change = on_change
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setChecked(bool(preferences.get(key)))
        self.setFixedHeight(28)
        self.clicked.connect(self._changed)
        self._render()

    def _changed(self) -> None:
        preferences.set_value(self._key, self.isChecked())
        self._render()
        if self._on_change:
            self._on_change(self.isChecked())

    def _render(self) -> None:
        on = self.isChecked()
        self.setText("On" if on else "Off")
        tone = colors.HOME_SUCCESS if on else colors.HOME_TEXT_MUTED
        edge = colors.HOME_SUCCESS if on else colors.HOME_BORDER_LIT
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent; border: 1px solid {edge};
                border-radius: 14px; color: {tone};
                font-size: 12px; padding: 0 18px;
            }}
            """
        )


class Panel(QFrame):
    """One titled block."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("panel")

        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(22, 18, 22, 18)
        self.body.setSpacing(10)

        head = QLabel(title)
        head.setObjectName("panel_title")
        self.body.addWidget(head)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("panel_sub")
            sub.setWordWrap(True)
            self.body.addWidget(sub)

    def row(self, label: str, widget: QWidget) -> None:
        line = QHBoxLayout()
        line.setSpacing(14)
        text = QLabel(label)
        text.setObjectName("row_label")
        line.addWidget(text, 1)
        line.addWidget(widget, 0)
        self.body.addLayout(line)

    def note(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("panel_note")
        label.setWordWrap(True)
        self.body.addWidget(label)


class SettingsPanel(QWidget):
    """Layer 5 surface — opened on demand, never part of the resting Home."""

    dismissed = Signal()

    def __init__(self, controller_hooks: dict | None = None) -> None:
        super().__init__()
        self._hooks = controller_hooks or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        inner = QWidget()
        self._column = QVBoxLayout(inner)
        self._column.setContentsMargins(34, 28, 34, 34)
        self._column.setSpacing(16)

        heading = QLabel("Mike")
        heading.setObjectName("settings_heading")
        self._column.addWidget(heading)

        caption = QLabel("Everything below runs on this Mac.")
        caption.setObjectName("settings_caption")
        self._column.addWidget(caption)

        self._column.addSpacing(6)

        self._column.addWidget(self._activity_panel())
        self._column.addWidget(self._voice_panel())
        self._column.addWidget(self._wake_panel())
        self._column.addWidget(self._memory_panel())
        self._column.addWidget(self._safety_panel())
        self._column.addWidget(self._privacy_panel())

        close = QPushButton("Close")
        close.setObjectName("settings_close")
        close.setCursor(Qt.PointingHandCursor)
        close.setFixedHeight(30)
        close.clicked.connect(self.dismissed.emit)
        self._column.addWidget(close, 0, Qt.AlignHCenter)

        self._column.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        scroll.viewport().setAutoFillBackground(False)
        inner.setAutoFillBackground(False)
        root.addWidget(scroll)

        self.setAutoFillBackground(True)
        self._apply_theme()

    # ── Panels ───────────────────────────────────────────────

    def _activity_panel(self) -> Panel:
        panel = Panel(
            "Activity",
            "What Mike has actually done. Recorded when a tool runs, from the "
            "result it returned — nothing here is a plan or an intention.",
        )

        self._activity_list = QVBoxLayout()
        self._activity_list.setSpacing(5)
        panel.body.addLayout(self._activity_list)

        self._activity_empty = QLabel()
        self._activity_empty.setObjectName("panel_note")
        panel.body.addWidget(self._activity_empty)

        clear = QPushButton("Clear history")
        clear.setObjectName("mem_forget")
        clear.setCursor(Qt.PointingHandCursor)
        clear.setFixedHeight(24)
        clear.clicked.connect(self._clear_activity)
        panel.body.addWidget(clear, 0, Qt.AlignRight)

        self._refresh_activity()
        return panel

    def _clear_activity(self) -> None:
        activity_store.clear()
        self._refresh_activity()

    def _refresh_activity(self) -> None:
        while self._activity_list.count():
            item = self._activity_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rows = activity_store.recent(limit=25)
        if not rows:
            self._activity_empty.setText("Nothing yet.")
            self._activity_empty.show()
            return

        self._activity_empty.hide()
        for row in rows:
            self._activity_list.addWidget(self._activity_row_widget(row))

    def _activity_row_widget(self, row: dict) -> QWidget:
        import datetime

        frame = QFrame()
        frame.setObjectName("mem_row")
        line = QHBoxLayout(frame)
        line.setContentsMargins(12, 7, 12, 7)
        line.setSpacing(10)

        ok = bool(row.get("succeeded"))
        mark = QLabel("✓" if ok else "✕")
        mark.setObjectName("act_mark")
        mark.setFixedWidth(14)
        mark.setStyleSheet(
            f"color: {colors.HOME_SUCCESS if ok else colors.HOME_ERROR};"
            " font-size: 11px; background: transparent; border: none;"
        )
        line.addWidget(mark)

        text = QLabel(row.get("action", ""))
        text.setObjectName("mem_text")
        text.setWordWrap(True)
        line.addWidget(text, 1)

        when = QLabel(
            datetime.datetime.fromtimestamp(row.get("started_at", 0)).strftime("%H:%M")
        )
        when.setObjectName("mem_tag")
        line.addWidget(when)

        return frame

    def _voice_panel(self) -> Panel:
        import voice.speaker as speaker

        panel = Panel(
            "Voice",
            "Speech is generated by macOS itself — no audio leaves the machine.",
        )
        panel.row(
            "Speak replies aloud",
            Toggle("voice_enabled", "voice", self._hooks.get("on_voice_toggle")),
        )
        panel.note(f"Currently using {speaker.VOICE} at {speaker.RATE} words per minute.")
        return panel

    def _wake_panel(self) -> Panel:
        from voice.wake_word import WAKE_PHRASES

        panel = Panel(
            "Wake word",
            "Listening happens locally and continuously while enabled.",
        )
        panel.row(
            "Listen for the wake word",
            Toggle("wake_word_enabled", "wake", self._hooks.get("on_wake_toggle")),
        )
        panel.note("Responds to: " + ", ".join(f"“{p}”" for p in WAKE_PHRASES[:2]))
        return panel

    def _memory_panel(self) -> Panel:
        panel = Panel(
            "Memory",
            "Things Mike has been explicitly asked to remember. Yours to edit.",
        )

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setObjectName("mem_search")
        self._search.setPlaceholderText("Search memories…")
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._refresh_memories)
        search_row.addWidget(self._search, 1)
        panel.body.addLayout(search_row)

        self._memory_list = QVBoxLayout()
        self._memory_list.setSpacing(6)
        panel.body.addLayout(self._memory_list)

        self._memory_empty = QLabel()
        self._memory_empty.setObjectName("panel_note")
        panel.body.addWidget(self._memory_empty)

        self._refresh_memories()
        return panel

    def _refresh_memories(self) -> None:
        while self._memory_list.count():
            item = self._memory_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self._search.text().strip() if hasattr(self, "_search") else ""
        try:
            result = memory_store.recall(query=query)
            entries = result.get("memories", [])
        except Exception:
            entries = []

        if not entries:
            self._memory_empty.setText(
                "Nothing remembered yet." if not query else "No matches."
            )
            self._memory_empty.show()
            return

        self._memory_empty.hide()

        for entry in entries[:40]:
            self._memory_list.addWidget(self._memory_row(entry))

    def _memory_row(self, entry: dict) -> QWidget:
        row = QFrame()
        row.setObjectName("mem_row")
        line = QHBoxLayout(row)
        line.setContentsMargins(12, 8, 8, 8)
        line.setSpacing(10)

        tag = QLabel(entry.get("category", "fact"))
        tag.setObjectName("mem_tag")
        tag.setFixedWidth(74)
        line.addWidget(tag)

        text = QLabel(entry.get("content", ""))
        text.setObjectName("mem_text")
        text.setWordWrap(True)
        line.addWidget(text, 1)

        forget = QPushButton("Forget")
        forget.setObjectName("mem_forget")
        forget.setCursor(Qt.PointingHandCursor)
        forget.setFixedHeight(24)
        forget.clicked.connect(lambda: self._forget(entry.get("id")))
        line.addWidget(forget)

        return row

    def _forget(self, memory_id) -> None:
        if memory_id is None:
            return
        try:
            memory_store.forget(memory_id=int(memory_id))
        except Exception:
            pass
        self._refresh_memories()

    def _safety_panel(self) -> Panel:
        panel = Panel(
            "Safety",
            "These always stop and ask first. The list is read from the gate "
            "itself, so it cannot drift from what actually happens.",
        )

        described = {
            "write_file": "Writing over a file",
            "delete_path": "Deleting a file or folder",
            "run_command": "Running a terminal command",
            "run_background": "Starting a background process",
            "ide_apply_edit": "Editing a file open in your editor",
        }

        for name in sorted(_CONFIRM_ACTIONS):
            panel.note("•  " + described.get(name, name.replace("_", " ").capitalize()))

        return panel

    def _privacy_panel(self) -> Panel:
        panel = Panel("Privacy", "")
        panel.note(
            "Mike runs entirely on this Mac. The model is local, memory is a file "
            "on this disk, speech is generated by macOS, and the editor bridge "
            "listens only on 127.0.0.1. Nothing is sent to a server, and there is "
            "no analytics or telemetry of any kind."
        )
        panel.note(f"Memory database:  {memory_store.db_path()}")
        panel.note(f"Preferences:  {preferences.path()}")
        return panel

    # ── Theme ────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            SettingsPanel {{ background: {colors.HOME_GROUND}; }}
            QScrollArea {{ background: {colors.HOME_GROUND}; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: {colors.HOME_GROUND}; }}
            QLabel#settings_heading {{
                color: {colors.HOME_TEXT}; font-size: 20px; font-weight: 600;
                background: transparent; border: none;
            }}
            QLabel#settings_caption {{
                color: {colors.HOME_TEXT_MUTED}; font-size: 13px;
                background: transparent; border: none;
            }}
            QFrame#panel {{
                background: {colors.HOME_SURFACE};
                border: 1px solid {colors.HOME_BORDER};
                border-radius: 14px;
            }}
            QLabel#panel_title {{
                color: {colors.HOME_ACCENT}; font-size: 11px; font-weight: 700;
                letter-spacing: 1.3px; text-transform: uppercase;
                background: transparent; border: none;
            }}
            QLabel#panel_sub {{
                color: {colors.HOME_TEXT_SECONDARY}; font-size: 13px;
                background: transparent; border: none;
            }}
            QLabel#panel_note {{
                color: {colors.HOME_TEXT_MUTED}; font-size: 12px;
                background: transparent; border: none;
            }}
            QLabel#row_label {{
                color: {colors.HOME_TEXT}; font-size: 14px;
                background: transparent; border: none;
            }}
            QLineEdit#mem_search {{
                background: {colors.HOME_GROUND};
                border: 1px solid {colors.HOME_BORDER};
                border-radius: 8px; color: {colors.HOME_TEXT};
                padding: 0 10px; font-size: 13px;
            }}
            QFrame#mem_row {{
                background: {colors.HOME_GROUND};
                border: 1px solid {colors.HOME_BORDER};
                border-radius: 9px;
            }}
            QLabel#mem_tag {{
                color: {colors.HOME_TEXT_MUTED}; font-size: 10px;
                font-family: "{typography.MONO_FONT}";
                background: transparent; border: none;
            }}
            QLabel#mem_text {{
                color: {colors.HOME_TEXT_SECONDARY}; font-size: 13px;
                background: transparent; border: none;
            }}
            QPushButton#mem_forget {{
                background: transparent; border: 1px solid {colors.HOME_BORDER_LIT};
                border-radius: 12px; color: {colors.HOME_TEXT_MUTED};
                font-size: 11px; padding: 0 12px;
            }}
            QPushButton#mem_forget:hover {{
                color: {colors.HOME_ERROR}; border-color: {colors.HOME_ERROR};
            }}
            QPushButton#settings_close {{
                background: transparent; border: 1px solid {colors.HOME_BORDER_LIT};
                border-radius: 15px; color: {colors.HOME_TEXT_SECONDARY};
                font-size: 12px; padding: 0 24px;
            }}
            QPushButton#settings_close:hover {{
                color: {colors.HOME_TEXT}; border-color: {colors.HOME_ACCENT};
            }}
            """
        )

    def refresh(self) -> None:
        self._refresh_memories()
        self._refresh_activity()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.dismissed.emit()
            return
        super().keyPressEvent(event)
