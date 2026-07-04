from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, Signal

from brain.runtime import MikeRuntime


class RuntimeWorker(QObject):
    """
    Executes MikeRuntime inside a worker thread.

    Responsibilities
    ----------------
    • Execute runtime requests
    • Return responses
    • Forward exceptions

    Never
    -----
    • Touch UI
    • Update widgets
    """

    finished = Signal(str)

    error = Signal(str)

    def __init__(
        self,
        runtime: MikeRuntime,
        message: str,
    ) -> None:

        super().__init__()

        self._runtime = runtime

        self._message = message

    # =====================================================

    def run(self) -> None:

        try:

            response = self._runtime.process(
                self._message
            )

            self.finished.emit(
                response
            )

        except Exception as exc:

            traceback.print_exc()

            self.error.emit(
                f"{type(exc).__name__}: {exc}"
            )