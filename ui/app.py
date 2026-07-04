from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
)

from brain.runtime import MikeRuntime

from ui.pages.chat_page import ChatPage
from ui.theme.stylesheet import GLOBAL_STYLESHEET
from ui.widgets.thinking_indicator import ThinkingState


# ==========================================================
# Runtime Worker
# ==========================================================


class RuntimeWorker(QObject):

    finished = Signal(str)

    error = Signal(str)

    def __init__(
        self,
        runtime: MikeRuntime,
        message: str,
    ) -> None:

        super().__init__()

        self.runtime = runtime

        self.message = message

    # -----------------------------------------------------

    def run(self) -> None:

        try:

            response = self.runtime.process(
                self.message
            )

            self.finished.emit(
                response
            )

        except Exception as exc:

            traceback.print_exc()

            self.error.emit(
                f"⚠ {type(exc).__name__}: {exc}"
            )


# ==========================================================
# Main Window
# ==========================================================


class MikeWindow(QMainWindow):
    """
    Mike Desktop Application.

    Presentation Layer only.

    Responsibilities
    ----------------
    • Build UI
    • Display conversation
    • Dispatch work to MikeRuntime
    • Display responses

    Runtime execution never blocks the UI.
    """

    # -----------------------------------------------------

    def __init__(self) -> None:

        super().__init__()

        self.runtime = MikeRuntime()

        self._thread: QThread | None = None

        self._worker: RuntimeWorker | None = None

        self._build_ui()

        self._connect_signals()

        self._startup()

    # =====================================================
    # Startup
    # =====================================================

    def _startup(self) -> None:

        self.page.status.set_text(
            "Starting Mike..."
        )

        QApplication.processEvents()

        try:

            greeting = self.runtime.startup()

            self.page.add_mike_message(
                greeting
            )

            self.page.status.set_text(
                "Ready"
            )

        except Exception:

            traceback.print_exc()

            self.page.add_mike_message(
                "Hello."
            )

            self.page.status.set_text(
                "Ready"
            )

    # =====================================================
    # UI
    # =====================================================

    def _build_ui(self) -> None:

        self.setWindowTitle("Mike")

        self.resize(
            1280,
            800,
        )

        self.setMinimumSize(
            1024,
            720,
        )

        self.page = ChatPage()

        self.setCentralWidget(
            self.page
        )

    # =====================================================
    # Signals
    # =====================================================

    def _connect_signals(self) -> None:

        self.page.input.submitted.connect(
            self.process_message
        )

        QShortcut(
            QKeySequence("Ctrl+L"),
            self,
            activated=self.page.conversation.clear,
        )

    # =====================================================
    # Conversation
    # =====================================================

    def process_message(
        self,
        message: str,
    ) -> None:

        message = message.strip()

        if not message:

            return

        self.page.add_user_message(
            message
        )

        self.page.header.set_state(
            ThinkingState.THINKING
        )

        self.page.status.set_text(
            "Thinking..."
        )

        self.page.input.set_enabled(
            False
        )

        self.page.conversation.show_thinking()

        self._thread = QThread()

        self._worker = RuntimeWorker(
            self.runtime,
            message,
        )

        self._worker.moveToThread(
            self._thread
        )

        self._thread.started.connect(
            self._worker.run
        )

        self._worker.finished.connect(
            self._on_response
        )

        self._worker.error.connect(
            self._on_error
        )

        self._worker.finished.connect(
            self._cleanup_worker
        )

        self._worker.error.connect(
            self._cleanup_worker
        )

        self._thread.start()

    # =====================================================

    def _on_response(
        self,
        response: str,
    ) -> None:

        self.page.conversation.hide_thinking()

        self.page.add_mike_message(
            response
        )

        self.page.status.set_text(
            "Ready"
        )

        self.page.header.set_state(
            ThinkingState.IDLE
        )

        self.page.input.set_enabled(
            True
        )

        self.page.input.focus()

    # =====================================================

    def _on_error(
        self,
        error: str,
    ) -> None:

        self.page.conversation.hide_thinking()

        self.page.add_mike_message(
            error
        )

        self.page.status.set_text(
            "Runtime Error"
        )

        self.page.header.set_state(
            ThinkingState.IDLE
        )

        self.page.input.set_enabled(
            True
        )

        self.page.input.focus()

    # =====================================================

    def _cleanup_worker(self) -> None:

        if self._thread is not None:

            self._thread.quit()

            self._thread.wait()

            self._thread.deleteLater()

            self._thread = None

        if self._worker is not None:

            self._worker.deleteLater()

            self._worker = None

    # =====================================================

    def closeEvent(
        self,
        event,
    ) -> None:

        if self._thread is not None:

            self._thread.quit()

            self._thread.wait()

        event.accept()


# ==========================================================
# Entry Point
# ==========================================================


def run() -> None:

    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        "Mike"
    )

    app.setStyleSheet(
        GLOBAL_STYLESHEET
    )

    window = MikeWindow()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":

    run()