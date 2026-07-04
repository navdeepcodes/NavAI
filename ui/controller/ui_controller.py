from __future__ import annotations

from PySide6.QtCore import QObject, QThread

from brain.runtime import MikeRuntime

from ui.controller.runtime_worker import RuntimeWorker
from ui.pages.chat_page import ChatPage


class UIController(QObject):
    """
    Coordinates the UI and MikeRuntime.

    Responsibilities
    ----------------
    • Receive user input
    • Dispatch runtime work
    • Update the presentation layer
    • Manage worker thread lifecycle

    Contains no business logic.
    """

    # =====================================================

    def __init__(
        self,
        runtime: MikeRuntime,
        page: ChatPage,
    ) -> None:

        super().__init__()

        self._runtime = runtime
        self._page = page

        self._thread: QThread | None = None
        self._worker: RuntimeWorker | None = None

        self._connect()

    # =====================================================

    def _connect(self) -> None:

        self._page.input.submitted.connect(
            self.process_message
        )

    # =====================================================

    def startup(self) -> None:

        greeting = self._runtime.startup()

        self._page.add_mike_message(
            greeting
        )

    # =====================================================

    def process_message(
        self,
        message: str,
    ) -> None:

        message = message.strip()

        if not message:
            return

        self._page.add_user_message(
            message
        )

        self._page.show_thinking()

        self._page.input.set_enabled(False)

        self._thread = QThread()

        self._worker = RuntimeWorker(
            self._runtime,
            message,
        )

        self._worker.moveToThread(
            self._thread
        )

        self._thread.started.connect(
            self._worker.run
        )

        self._worker.finished.connect(
            self._response_ready
        )

        self._worker.error.connect(
            self._response_error
        )

        self._worker.finished.connect(
            self._cleanup
        )

        self._worker.error.connect(
            self._cleanup
        )

        self._thread.start()

    # =====================================================

    def _response_ready(
        self,
        response: str,
    ) -> None:

        self._page.hide_thinking()

        self._page.add_mike_message(
            response
        )

        self._page.input.set_enabled(True)

        self._page.input.focus()

    # =====================================================

    def _response_error(
        self,
        error: str,
    ) -> None:

        self._page.hide_thinking()

        self._page.add_mike_message(
            error
        )

        self._page.input.set_enabled(True)

        self._page.input.focus()

    # =====================================================

    def _cleanup(self) -> None:

        if self._thread is not None:

            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()

            self._thread = None

        if self._worker is not None:

            self._worker.deleteLater()

            self._worker = None

    # =====================================================

    def shutdown(self) -> None:

        if self._thread is not None:

            self._thread.quit()
            self._thread.wait()

            self._thread.deleteLater()

            self._thread = None