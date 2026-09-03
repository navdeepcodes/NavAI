from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, Signal

from brain.core_runtime import CoreRuntime


class CoreRuntimeWorker(QObject):

    token = Signal(str)
    tool_start = Signal(str)
    tool_end = Signal(str)
    finished = Signal()
    error = Signal(str)
    confirmation_needed = Signal(str)

    def __init__(
        self,
        runtime: CoreRuntime,
        message: str,
    ) -> None:

        super().__init__()

        self._runtime = runtime
        self._message = message

        self._confirm_event = threading.Event()
        self._confirm_result = False
        self._awaiting_confirmation = False

        self._cancel_event = threading.Event()

    # =====================================================

    def run(self) -> None:

        try:

            for event_type, payload in self._runtime.process_streaming(
                self._message,
                confirm_callback=self._request_confirmation,
                cancel_event=self._cancel_event,
            ):
                if event_type == "token":
                    self.token.emit(payload)
                elif event_type == "tool_start":
                    self.tool_start.emit(payload)
                elif event_type == "tool_end":
                    self.tool_end.emit(payload)

            self.finished.emit()

        except Exception as exc:

            traceback.print_exc()

            self.error.emit(
                f"{type(exc).__name__}: {exc}"
            )

    # =====================================================

    def _request_confirmation(self, description: str) -> bool:

        self._confirm_event.clear()
        self._awaiting_confirmation = True

        self.confirmation_needed.emit(description)

        self._confirm_event.wait()

        self._awaiting_confirmation = False

        return self._confirm_result

    # =====================================================

    def set_confirmation(self, approved: bool) -> None:

        self._confirm_result = approved

        self._confirm_event.set()

    # =====================================================

    def cancel(self) -> None:
        """
        Stops the agent loop from starting its next step. If it's currently
        blocked waiting on a confirmation dialog, that wait is released as a
        denial first, so the thread doesn't hang waiting for input that will
        never come from a cancelled turn.
        """

        self._cancel_event.set()

        if self._awaiting_confirmation:
            self.set_confirmation(False)
