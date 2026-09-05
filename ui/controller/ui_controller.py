from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer

from brain import activity_store, projects
from brain.core_runtime import CoreRuntime
from config import preferences
from ui.controller.core_worker import CoreRuntimeWorker
from ui.instrument.edge import EdgeStrip
from ui.instrument.home import HomeSurface
from ui.instrument.invoke import InvokeLine
from voice.speaker import Speaker
from voice.voice_input import VoiceInputManager
from voice.wake_word import WakeWordDetector
from logs.logger import logger


class UIController(QObject):

    def __init__(
        self,
        runtime: CoreRuntime,
        page: HomeSurface,
        floating: InvokeLine | None = None,
        edge: EdgeStrip | None = None,
    ) -> None:

        super().__init__()

        self._runtime = runtime
        self._page = page
        self._floating = floating
        self._edge = edge

        self._thread: QThread | None = None
        self._worker: CoreRuntimeWorker | None = None
        self._retired_threads: list[QThread] = []
        self._retired_by_worker: dict = {}
        self._stream_bubble = None
        self._action_card = None
        self._activity_row: int | None = None

        self._voice = VoiceInputManager()
        self._speaker = Speaker()
        self._response_text = ""
        self._spoken_up_to = 0
        self._speech_pump_timer = QTimer()
        self._speech_pump_timer.setInterval(100)
        self._speech_pump_timer.timeout.connect(self._pump_speech)

        self._wake = WakeWordDetector(on_wake=self._on_wake_word)

        self._connect()

    def _connect(self) -> None:

        self._page.input.submitted.connect(
            self.process_message
        )

        self._page.conversation.suggestion_clicked.connect(
            self.process_message
        )

        self._page.input.voice.clicked_voice.connect(
            self._on_voice_button
        )

        self._voice.state_changed.connect(
            self._on_voice_state
        )

        self._voice.transcription_ready.connect(
            self._on_voice_text
        )

        self._voice.auto_stopped.connect(
            self._on_auto_stopped
        )

        self._voice.error.connect(
            self._on_voice_error
        )

        self._page.activity.stop_requested.connect(
            self.cancel_active
        )

        self._page.confirm.approved.connect(
            lambda: self._resolve_confirmation(True)
        )

        self._page.confirm.denied.connect(
            lambda: self._resolve_confirmation(False)
        )

        if self._floating:
            self._floating.message_submitted.connect(
                self._on_floating_submit
            )
            self._floating.cancel_requested.connect(
                self.cancel_active
            )

    def startup(self) -> None:

        if preferences.get("wake_word_enabled", True):
            self._wake.start()

    def _on_floating_submit(self, text: str) -> None:
        self._floating.clear_response()
        self._floating.set_state("thinking")
        self.process_message(text)

    def process_message(self, message: str) -> None:

        message = message.strip()

        if not message:
            return

        self._retire_active_worker()

        self._mirror_edge("thinking")

        self._page.add_user_message(message)

        self._page.show_thinking()

        self._page.input.set_enabled(False)

        self._stream_bubble = None
        self._action_card = None
        self._response_text = ""
        self._speaker.stop()

        if self._floating and self._floating.isVisible():
            self._floating.clear_response()
            self._floating.set_state("thinking")

        self._thread = QThread()

        self._worker = CoreRuntimeWorker(
            self._runtime,
            message,
        )

        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)

        self._worker.token.connect(self._on_token)
        self._worker.tool_start.connect(self._on_tool_start)
        self._worker.tool_end.connect(self._on_tool_end)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.confirmation_needed.connect(
            self._show_confirmation
        )

        self._worker.finished.connect(self._cleanup)
        self._worker.error.connect(self._cleanup)

        self._thread.start()

    def _on_token(self, text: str) -> None:

        self._page.hide_thinking()

        if self._stream_bubble is None:
            self._stream_bubble = self._page.begin_mike_stream()
            # Deliberately not suppressing the wake word here — this is what
            # lets "Hey Mike" interrupt him mid-sentence. Verified empirically
            # against this machine's own TTS output (twice, saying the wake
            # phrase itself) with zero false triggers before relying on it.
            self._page.input.voice.set_state("speaking")
            self._speech_pump_timer.start()

            if self._floating and self._floating.isVisible():
                self._floating.set_state("speaking")

        self._stream_bubble.append_text(text)
        self._response_text += text
        self._try_speak_sentences()

        if self._floating and self._floating.isVisible():
            self._floating.append_response(text)

        QTimer.singleShot(
            0,
            self._page.conversation.scroll_to_bottom,
        )

    def _try_speak_sentences(self) -> None:
        if not self._speech_allowed():
            return
        pending = self._response_text[self._spoken_up_to:]
        import re
        parts = re.split(r'(?<=[.!?])\s+', pending)
        if len(parts) > 1:
            for sentence in parts[:-1]:
                if sentence.strip():
                    self._speaker.speak_sentence(sentence)
            self._spoken_up_to = len(self._response_text) - len(parts[-1])

    def _pump_speech(self) -> None:
        self._speaker.pump()
        if self._speaker.streaming_done and not self._speaker.is_speaking():
            self._speech_pump_timer.stop()
            self._page.input.voice.set_state("idle")
            self._wake.resume()

            if self._floating and self._floating.isVisible():
                self._floating.finish()

    # The edge exists for when Mike has no other surface on screen. If the
    # Home or the floating input is already up, a second strip saying the same
    # thing is just clutter.
    _EDGE_WORTH_A_GLANCE = ("working", "needs_user", "error")

    def _edge_available(self) -> bool:

        if self._edge is None:
            return False

        if self._floating is not None and self._floating.isVisible():
            return False

        window = self._page.window()
        if window is not None and window.isVisible() and not window.isMinimized():
            return False

        return True

    def _mirror_edge(self, state: str, text: str = "") -> None:
        """
        Reflects real state, but only states a person would actually want to
        catch out of the corner of their eye. "Thinking" is not one of them.
        """

        if self._edge is None:
            return

        try:
            if not self._edge_available():
                self._edge.dismiss()
                return

            if state in self._EDGE_WORTH_A_GLANCE:
                self._edge.show_state(state, text)
            else:
                self._edge.dismiss()

        except Exception:
            logger.exception("Edge surface update failed.")

    def _on_tool_start(self, description: str) -> None:

        self._mirror_edge("working", description)

        self._page.hide_thinking()

        self._stream_bubble = None

        self._action_card = self._page.add_action_card(
            description
        )

        # Recorded when it starts, closed out with the tool's real result.
        # Tagged with whatever project is attached right now (via the IDE
        # workspace root), so this can be filtered per-project later without
        # a second table — untagged rows just mean "no project was open".
        self._activity_row = activity_store.begin(description, project_id=projects.current())

        if self._floating and self._floating.isVisible():
            self._floating.show_tool_status(description)

    def _on_tool_end(self, status: str) -> None:

        is_failure = (
            "error" in status.lower()
            or "failed" in status.lower()
            or "cancelled" in status.lower()
            or "denied" in status.lower()
        )
        activity_store.complete(self._activity_row, status, not is_failure)

        # If this action was a write or delete, tools/filesystem/actions.py
        # captured a before-state snapshot right before touching disk — link
        # it to this row now that the row actually has an id. Only on real
        # success: a snapshot from a failed write describes a change that
        # never actually happened, so there's nothing to offer reverting.
        if not is_failure and self._activity_row is not None:
            try:
                from brain import revert_store
                revert_store.attach_to_activity(self._activity_row)
            except Exception:
                logger.exception("Could not attach revert snapshot.")

        self._activity_row = None

        if self._action_card is not None:
            is_error = (
                "error" in status.lower()
                or "failed" in status.lower()
                or "cancelled" in status.lower()
                or "denied" in status.lower()
            )
            label = ""
            if hasattr(self._action_card, '_label'):
                label = self._action_card._label.text()
            self._action_card.mark_done(success=not is_error)
            self._action_card = None

            if self._floating and self._floating.isVisible():
                self._floating.show_tool_done(label or status[:40], success=not is_error)

    def _finalize_retired_activity(self, row_id: int, status: str) -> None:
        """
        Same bookkeeping as _on_tool_end, for a tool_start that already fired
        on a worker retired mid-turn (cancelled, or superseded by a new
        message) before its tool_end arrived. Deliberately doesn't touch
        stream/action-card/edge state — that all belongs to whatever turn is
        current now, not to this one.
        """

        is_failure = (
            "error" in status.lower()
            or "failed" in status.lower()
            or "cancelled" in status.lower()
            or "denied" in status.lower()
        )
        activity_store.complete(row_id, status, not is_failure)

        if not is_failure:
            try:
                from brain import revert_store
                revert_store.attach_to_activity(row_id)
            except Exception:
                logger.exception("Could not attach revert snapshot.")

    def _on_finished(self) -> None:

        self._page.hide_thinking()

        remainder = self._response_text[self._spoken_up_to:].strip()
        if remainder and self._speech_allowed():
            self._speaker.speak_sentence(remainder)
        self._speaker.finish_streaming()

        if (self._speech_allowed()
                and not self._speech_pump_timer.isActive()
                and self._response_text.strip()):
            # Same as _on_token: left un-suppressed on purpose, for barge-in.
            self._page.input.voice.set_state("speaking")
            self._speech_pump_timer.start()

            if self._floating and self._floating.isVisible():
                self._floating.set_state("speaking")

        if not self._response_text.strip():
            if self._floating and self._floating.isVisible():
                self._floating.finish()

        answer = self._response_text.strip()

        self._stream_bubble = None
        self._action_card = None
        self._response_text = ""
        self._spoken_up_to = 0

        self._page.set_state("idle")

        # The edge carries the answer only when the Home isn't already
        # showing it — otherwise the same text would appear twice.
        if answer and self._edge_available():
            self._edge.show_message(answer)
        elif self._edge is not None:
            self._edge.dismiss()

        self._page.input.set_enabled(True)
        self._page.input.focus()

    def _on_error(self, error: str) -> None:

        self._page.hide_thinking()

        readable = _humanize_error(error)

        self._page.add_mike_message(readable)
        self._page.set_state("error")
        self._mirror_edge("error", readable)

        if self._floating and self._floating.isVisible():
            self._floating.set_response(readable)
            self._floating.finish()

        self._stream_bubble = None
        self._action_card = None

        self._page.input.set_enabled(True)
        self._page.input.focus()

    def _show_confirmation(self, description: str) -> None:
        """
        The worker thread is parked on an event until this resolves, so the
        prompt is shown inline rather than as a modal — same gate, no dialog.
        """

        self._state_before_confirm = self._page.state()

        self._page.set_state("needs_user")
        self._page.confirm.ask(description)
        self._mirror_edge("needs_user", "Waiting for your approval")

    def _resolve_confirmation(self, approved: bool) -> None:

        self._page.confirm.hide()

        restore = getattr(self, "_state_before_confirm", "working")
        self._page.set_state(restore if restore != "needs_user" else "working")

        if self._worker is not None:
            self._worker.set_confirmation(approved)

    # =====================================================
    # Voice interaction
    # =====================================================

    def voice_shortcut_pressed(self) -> None:
        if self._floating and not self._floating.isVisible():
            self._floating.activate(start_listening=True)

        if self._speaker.is_speaking():
            self._speaker.stop()
            self._wake.resume()
            self._page.input.voice.set_state("idle")
            QTimer.singleShot(150, self._start_voice)
        elif self._voice.state == "idle":
            self._start_voice()
        elif self._voice.state == "recording":
            self._voice.stop_recording()

    def _start_voice(self) -> None:
        self._wake.suppress()
        self._voice.start_recording()

    def _on_voice_button(self) -> None:

        if self._speaker.is_speaking():
            self._speaker.stop()
            self._wake.resume()
            self._page.input.voice.set_state("idle")
            QTimer.singleShot(150, self._start_voice)
            return

        if self._voice.state == "idle":
            self._start_voice()
        elif self._voice.state == "recording":
            self._voice.stop_recording()

    def _on_voice_state(self, state: str) -> None:

        self._page.input.voice.set_state(state)

        # Real mic state drives the Home's presence, but never while Mike is
        # mid-task or waiting on an approval.
        if self._page.state() not in ("working", "needs_user"):
            if state == "recording":
                self._page.set_state("listening")
            elif state == "transcribing":
                self._page.set_state("thinking")
            elif state == "idle" and self._page.state() == "listening":
                self._page.set_state("idle")

        if self._floating and self._floating.isVisible():
            if state == "recording":
                self._floating.set_state("listening")
            elif state == "transcribing":
                self._floating.set_state("transcribing")
            elif state == "idle":
                pass

        if state == "idle":
            self._wake.resume()

    def _on_auto_stopped(self) -> None:

        logger.info("Voice auto-stopped (silence detected)")

    def _on_voice_text(self, text: str) -> None:

        self._speaker.stop()

        if self._floating and self._floating.isVisible():
            self._floating.set_state("thinking")

        self.process_message(text)

    def _on_voice_error(self, message: str) -> None:

        self._page.add_mike_message(message)

        if self._floating and self._floating.isVisible():
            self._floating.set_response(message)
            self._floating.finish()

    def _on_wake_word(self) -> None:

        logger.info("Wake word activated")

        if self._speaker.is_speaking():
            # Barge-in: the wake word firing mid-sentence means "stop talking,
            # I'm saying something now." Stopping the pump timer here too,
            # not just the speaker — otherwise its next tick (up to 100ms
            # away) sees streaming_done and calls floating.finish(), which
            # would stomp the "listening" state activate() is about to set.
            self._speaker.stop()
            self._speech_pump_timer.stop()
            self._page.input.voice.set_state("idle")

        if self._floating:
            self._floating.activate(start_listening=True)

        if self._voice.state == "idle":
            QTimer.singleShot(0, self._start_voice)

    # =====================================================
    # Preferences applied to the live engines
    # =====================================================

    def set_voice_enabled(self, enabled: bool) -> None:
        """Turning speech off should silence Mike immediately, not next turn."""

        if not enabled:
            self._speaker.stop()
            self._speech_pump_timer.stop()
            self._page.input.voice.set_state("idle")

    def set_wake_word_enabled(self, enabled: bool) -> None:

        try:
            if enabled:
                self._wake.start()
            else:
                self._wake.stop()
        except Exception:
            logger.exception("Could not change wake word state.")

    def _speech_allowed(self) -> bool:
        return bool(preferences.get("voice_enabled", True))

    # =====================================================
    # Cancellation
    # =====================================================

    def _retire_active_worker(self) -> None:
        """
        Tells a currently-running worker to stop and detaches it from the
        UI-facing handlers, so its eventual finished/error signal can't fire
        against state that now belongs to a new turn. The retired worker
        tears itself down independently once it actually stops.
        """

        if self._worker is None:
            return

        old_worker = self._worker
        old_thread = self._thread

        # If a tool_start already fired for this worker, its matching
        # tool_end hasn't arrived yet — that one event still needs to close
        # out the activity row and claim any revert snapshot the tool
        # captured before disk was touched. Losing it would strand the row
        # at "in progress" forever and, for a write/delete, make its
        # snapshot permanently unreachable (attach_to_activity is the only
        # thing that ever links it to a row the UI can show). Route just
        # that one pending row to a finalizer instead of the normal
        # handler, which would also touch UI state that now belongs to
        # whatever comes next.
        pending_row = self._activity_row

        for signal, slot in (
            (old_worker.token, self._on_token),
            (old_worker.tool_start, self._on_tool_start),
            (old_worker.finished, self._on_finished),
            (old_worker.error, self._on_error),
            (old_worker.confirmation_needed, self._show_confirmation),
            (old_worker.finished, self._cleanup),
            (old_worker.error, self._cleanup),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

        try:
            old_worker.tool_end.disconnect(self._on_tool_end)
        except (TypeError, RuntimeError):
            pass

        if pending_row is not None:
            old_worker.tool_end.connect(
                lambda status, row=pending_row: self._finalize_retired_activity(row, status)
            )
        self._activity_row = None

        # Tracked so shutdown can wait on it — a retired thread that's still
        # finishing when the app closes otherwise gets destroyed mid-run.
        self._retired_threads.append(old_thread)
        self._retired_by_worker[old_worker] = old_thread

        # Deliberately a bound method of this controller rather than a local
        # closure: the controller lives on the GUI thread, so Qt queues the
        # call there. A plain closure has no thread affinity and would run on
        # the worker's own thread, where quit()/wait() would wait on itself.
        old_worker.finished.connect(self._on_retired_worker_finished)
        old_worker.error.connect(self._on_retired_worker_finished)

        old_worker.cancel()

    def _on_retired_worker_finished(self) -> None:

        worker = self.sender()
        thread = self._retired_by_worker.pop(worker, None)

        if thread is not None:
            thread.quit()
            thread.wait(3000)
            if thread in self._retired_threads:
                self._retired_threads.remove(thread)
            thread.deleteLater()

        if worker is not None:
            worker.deleteLater()

    def cancel_active(self) -> None:
        """
        User-triggered cancellation of whatever Mike is currently doing,
        with no new message following it.
        """

        if self._worker is None:
            return

        self._retire_active_worker()

        self._speaker.stop()
        self._speech_pump_timer.stop()
        self._page.hide_thinking()

        self._stream_bubble = None
        self._action_card = None

        self._page.confirm.hide()
        self._page.add_mike_message("Cancelled.")
        self._page.set_state("idle")
        self._mirror_edge("idle")

        if self._floating and self._floating.isVisible():
            self._floating.set_response("Cancelled.")
            self._floating.finish()

        self._page.input.set_enabled(True)
        self._page.input.focus()
        self._page.input.voice.set_state("idle")
        self._wake.resume()

        self._worker = None
        self._thread = None

    # =====================================================
    # Lifecycle
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

    def shutdown(self) -> None:

        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True

        self._speaker.stop()
        self._wake.stop()

        if self._worker is not None:
            self._worker.cancel()

        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()
            self._thread = None

        # Retired workers may still be mid-step; give them a bounded window to
        # unwind rather than tearing their threads down underneath them.
        for thread in list(self._retired_threads):
            thread.quit()
            thread.wait(3000)

        self._retired_threads.clear()


def _humanize_error(error: str) -> str:

    if "connection" in error.lower() or "refused" in error.lower():
        # A generic "make sure it's running" makes the user go troubleshoot
        # blind. A real check, run right now, tells them which of the two
        # actual causes it is and gives the exact fix for that one.
        try:
            from brain.diagnostics import check_ollama
            result = check_ollama()
            if result["reachable"] and result["model_pulled"]:
                # The check itself passed — this was a one-off hiccup, not
                # Ollama actually being down. Say that, not "couldn't reach".
                return (
                    "That request didn't go through, but Ollama and the "
                    "model both check out fine — try again."
                )
            return f"I couldn't reach the local model.\n\n{result['detail']}"
        except Exception:
            return (
                "I couldn't reach the local model.\n\n"
                "Make sure Ollama is running and try again."
            )

    if "timeout" in error.lower():
        return "That took too long. Try again with a simpler request."

    parts = error.split(": ", 1)
    if len(parts) == 2:
        return f"Something went wrong.\n\n{parts[1]}"

    return f"Something went wrong.\n\n{error}"
