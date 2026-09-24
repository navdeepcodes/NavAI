from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, Signal

from brain.core_runtime import CoreRuntime


class CoreRuntimeWorker(QObject):

    token = Signal(str)
    tool_start = Signal(str)
    tool_progress = Signal(str)
    tool_end = Signal(str)
    finished = Signal()
    error = Signal(str)
    confirmation_needed = Signal(str)

    def __init__(
        self,
        runtime: CoreRuntime,
        message: str,
        attachments: list[str] | None = None,
    ) -> None:

        super().__init__()

        self._runtime = runtime
        self._message = message
        self._attachments = list(attachments or [])

        self._confirm_event = threading.Event()
        self._confirm_result = False
        self._awaiting_confirmation = False

        self._cancel_event = threading.Event()

    # =====================================================

    def run(self) -> None:

        try:

            message = self._message
            if self._attachments:
                # Read the files here, off the GUI thread, and fold their
                # contents into the message so Mike always has them -- rather
                # than hoping the small model decides to call a read tool. A
                # document becomes its text, an image its description.
                message = self._with_attachments(message)

            for event_type, payload in self._runtime.process_streaming(
                message,
                confirm_callback=self._request_confirmation,
                cancel_event=self._cancel_event,
            ):
                if event_type == "token":
                    self.token.emit(payload)
                elif event_type == "tool_start":
                    self.tool_start.emit(payload)
                elif event_type == "tool_progress":
                    self.tool_progress.emit(payload)
                elif event_type == "tool_end":
                    self.tool_end.emit(payload)

            self.finished.emit()

        except Exception as exc:

            traceback.print_exc()

            self.error.emit(
                f"{type(exc).__name__}: {exc}"
            )

    # =====================================================

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}
    _MAX_DOC_CHARS = 12000        # a budget so one huge PDF can't swamp the turn

    def _with_attachments(self, message: str) -> str:
        import os

        blocks = []
        for path in self._attachments:
            name = os.path.basename(path)
            self.tool_start.emit(f"Reading {name}")
            content = self._read_one(path)
            self.tool_end.emit("done")
            blocks.append(
                f"[The user attached a file: {name}]\n{content}\n"
                f"[end of {name}]")

        preamble = "\n\n".join(blocks)
        if message.strip():
            return f"{preamble}\n\n{message}"
        # No words, just a file: give Mike a sensible default intent.
        return f"{preamble}\n\nHave a look at this and tell me what you make of it."

    def _read_one(self, path: str) -> str:
        import os

        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in self._IMAGE_EXTS:
                from vision.vision import Vision

                desc = Vision().analyze(
                    path,
                    "Describe this image in full: any text, equations, "
                    "diagrams, code or handwriting shown, and what it depicts.")
                return f"(an image; here is what it shows)\n{desc}"
            from tools.filesystem.document_reader import read_document

            text = read_document(path) or ""
            if len(text) > self._MAX_DOC_CHARS:
                text = text[:self._MAX_DOC_CHARS] + "\n...[truncated]"
            return text or "(the file appears to be empty)"
        except Exception as exc:
            return f"(couldn't read this file: {exc})"

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
