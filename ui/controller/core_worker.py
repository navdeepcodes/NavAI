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
    #: A tool call still being written: what it will do ("Writing style.css")
    preparing = Signal(str)
    finished = Signal()
    error = Signal(str)
    #: (what Mike wants to do, the session-long approval on offer or "")
    confirmation_needed = Signal(str, str)

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
                elif event_type == "preparing":
                    self.preparing.emit(payload)

            self.finished.emit()

        except Exception as exc:

            traceback.print_exc()

            self.error.emit(
                f"{type(exc).__name__}: {exc}"
            )

    # =====================================================

    def _with_attachments(self, message: str) -> str:
        """Each attached file as facts (name, full path, what it is) and a
        preview: Mike needs the path to DO anything with it -- merge, convert,
        read the rest (tools/documents/attach.py)."""
        from tools.documents import attach

        def each(name: str, starting: bool) -> None:
            if starting:
                self.tool_start.emit(f"Reading {name}")
            else:
                self.tool_end.emit("done")

        preamble = attach.describe_all(self._attachments, describe_image=self._describe_image, on_each=each)
        if message.strip():
            return f"{preamble}\n\n{message}"
        # No words, just a file: give Mike a sensible default intent.
        return f"{preamble}\n\nHave a look at this and tell me what you make of it."

    @staticmethod
    def _describe_image(path: str) -> str:
        """The picture model's description of a picture with no text in it."""
        try:
            from vision.vision import Vision

            return Vision().analyze(
                path,
                "Describe this image in full: any equations, diagrams, code or "
                "handwriting shown, and what it depicts.")
        except Exception as exc:
            return f"(couldn't describe it: {exc})"

    def _request_confirmation(self, description: str):
        """True, False, or "always" (allowed for the session)."""

        self._confirm_event.clear()
        self._awaiting_confirmation = True

        self.confirmation_needed.emit(
            description, str(getattr(self._runtime, "pending_offer", "") or ""))

        self._confirm_event.wait()

        self._awaiting_confirmation = False

        return self._confirm_result

    # =====================================================

    def set_confirmation(self, approved) -> None:
        """True, False, or "always": yes, and for the rest of the session."""

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
