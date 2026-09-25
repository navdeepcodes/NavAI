from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, QTimer

from brain import activity_store, conversation_store, projects
from brain.core_runtime import CoreRuntime
from config import preferences
from ui.controller.core_worker import CoreRuntimeWorker
from voice.speaker import Speaker
from voice.voice_input import VoiceInputManager
from voice.wake_word import WakeWordDetector
from logs.logger import logger

if TYPE_CHECKING:
    from ui.workspace.corner import CornerPresence
    from ui.workspace.workspace import MikeWorkspace


class UIController(QObject):

    def __init__(
        self,
        runtime: CoreRuntime,
        page: MikeWorkspace,
        floating: CornerPresence | None = None,
    ) -> None:

        super().__init__()

        self._runtime = runtime
        self._page = page
        self._floating = floating

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
        # The text of the bubble being streamed right now. A turn can hold
        # several bubbles (a sentence before a tool, the answer after it), and
        # each must end holding only its own words.
        self._bubble_text = ""
        self._spoken_up_to = 0
        self._speech_pump_timer = QTimer()
        self._speech_pump_timer.setInterval(100)
        self._speech_pump_timer.timeout.connect(self._pump_speech)

        self._wake = WakeWordDetector(on_wake=self._on_wake_word)

        # Lets the speech-to-text prewarm's initial wait be cut short on
        # shutdown, so a window torn down within a few seconds of opening
        # doesn't leave a thread sleeping — which a rapid open/close cycle
        # otherwise accumulates one at a time.
        self._prewarm_stop = threading.Event()
        self._prewarm_thread: threading.Thread | None = None

        # The saved conversation this chat belongs to. Created lazily on the
        # first message, so opening Mike and closing him again doesn't leave
        # empty chats cluttering History.
        self._conversation_id: int | None = None
        self.mission_welcome = ""

        # What the user is getting done, kept true from the files themselves.
        from ui.controller.mission_tracker import MissionTracker
        self._missions = MissionTracker(self)
        self._missions.changed.connect(self._on_mission_changed)

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

        mission_bar = getattr(self._page, "mission", None)
        if mission_bar is not None:
            mission_bar.drop_requested.connect(self._drop_mission)

        if self._floating:
            self._floating.message_submitted.connect(
                self._on_floating_submit
            )
            self._floating.cancel_requested.connect(
                self.cancel_active
            )

    def startup(self) -> None:

        # Reopening Mike continues the chat you were in, if it's recent. Done
        # before the model warm-up below so the warmed prefix is the one the
        # next question will actually use.
        self.resume_recent_conversation()
        self._missions.start()

        if preferences.get("wake_word_enabled", True):
            self._wake.start()

        # Pay the model's cold prefill now, off the GUI thread, while the
        # user is still reading the greeting -- see CoreRuntime.warm(). On a
        # machine with no GPU offload path this is the difference between a
        # first reply that lands in seconds and one that takes minutes.
        # Daemon so it can never hold up quitting, and it touches nothing
        # the UI owns.
        threading.Thread(
            target=self._runtime.warm, name="model-warm", daemon=True,
        ).start()

        # Load the speech-to-text model now too, so the first spoken turn
        # doesn't freeze on a first-run download. Started a few seconds behind
        # the brain warm so the window paints and the greeting speaks first,
        # then the (network-bound) model download runs while the user reads.
        # Only when voice is actually in play — no point pulling ~1.5GB for
        # someone who has turned voice off.
        if preferences.get("voice_enabled", True) or preferences.get("wake_word_enabled", True):
            def _prewarm_stt() -> None:
                # Interruptible wait: if the window is torn down first, this
                # returns immediately instead of holding a sleeping thread.
                if self._prewarm_stop.wait(3):
                    return
                try:
                    from voice.recognizer import get_recognizer
                    get_recognizer().prewarm()
                except Exception:
                    logger.exception("Speech-to-text prewarm failed.")
            self._prewarm_thread = threading.Thread(
                target=_prewarm_stt, name="stt-prewarm", daemon=True)
            self._prewarm_thread.start()

    def _on_floating_submit(self, text: str) -> None:
        self._floating.clear_response()
        self._floating.set_state("thinking")
        self.process_message(text)

    def process_message(self, message: str) -> None:

        message = message.strip()

        # An attachment on its own is a real turn ("here, read this"), so a
        # message is allowed to be empty as long as something was attached.
        attachments = self._page.take_attachments()
        if not message and not attachments:
            return

        self._retire_active_worker()


        self._page.add_user_message(message, attachments=attachments)

        # Keep what was said, so the chat survives a restart and shows up in
        # History. Attachments are recorded by name — the file itself stays
        # where the user keeps it.
        if self._conversation_id is None:
            self._conversation_id = conversation_store.create()
        import os as _os
        conversation_store.add_message(
            self._conversation_id, "user", message,
            [_os.path.basename(a) for a in attachments],
        )
        self._notify_conversation()

        self._page.show_thinking()

        self._page.input.set_enabled(False)

        self._stream_bubble = None
        self._action_card = None
        self._response_text = ""
        self._speaker.stop()
        # A new turn is the right moment to give the preferred voice another
        # go. Retrying mid-reply turns one failure into a stutter of them;
        # never retrying disables the voice for the session after a single
        # bad utterance.
        self._speaker.reset_health()

        if self._floating and self._floating.isVisible():
            self._floating.clear_response()
            self._floating.set_state("thinking")

        self._thread = QThread()

        self._worker = CoreRuntimeWorker(
            self._runtime,
            message,
            attachments=attachments,
        )

        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)

        self._worker.token.connect(self._on_token)
        self._worker.tool_start.connect(self._on_tool_start)
        self._worker.tool_progress.connect(self._on_tool_progress)
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
            self._bubble_text = ""
            # Deliberately not suppressing the wake word here — this is what
            # lets "Hey Mike" interrupt him mid-sentence. Verified empirically
            # against this machine's own TTS output (twice, saying the wake
            # phrase itself) with zero false triggers before relying on it.
            # Only shown as speaking when there is actually a voice: with
            # speech turned off, the mic claiming "speaking" was a small lie.
            if self._speech_allowed():
                self._page.input.voice.set_state("speaking")
            self._speech_pump_timer.start()

            if self._floating and self._floating.isVisible():
                self._floating.set_state("speaking")

        self._stream_bubble.append_text(text)
        self._bubble_text += text
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

            # Speech finishing is the real end of the turn, so this is where
            # Mike goes quiet — not when the *text* finished generating. Only
            # from "speaking", because by now a new turn may already own the
            # panel and this tick must not drag it back to idle.
            if self._page.state() == "speaking":
                self._page.set_state("idle")

            if self._floating and self._floating.isVisible():
                self._floating.finish()

    def _on_tool_start(self, description: str) -> None:


        self._page.hide_thinking()

        # What Mike said before this step is finished: give it its full
        # render, without the "Copy" a final answer carries.
        if self._stream_bubble is not None:
            try:
                self._stream_bubble.set_text(self._bubble_text, final=False)
            except TypeError:
                self._stream_bubble.set_text(self._bubble_text)
        self._stream_bubble = None
        self._bubble_text = ""

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

    def _on_tool_progress(self, description: str) -> None:
        """Updates the current row's own text in place -- for a step like a
        model download, whose duration is real (minutes, not the second or
        two most tool calls take) and worth narrating as it goes, rather
        than a card whose label is fixed the moment it appears."""
        if self._action_card is not None and hasattr(self._action_card, "update_text"):
            self._action_card.update_text(description)


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

        # The dead gap. A finished step settles to a static tick, and the
        # model then takes seconds-to-a-minute composing what it will say
        # about it -- during which nothing on screen moved at all. Watching a
        # motionless "done" row for a minute reads as a hang, which is the
        # exact thing the thinking animation exists to prevent; it was just
        # never brought back after the first tool call took it away.
        # _on_token hides it again the instant the reply starts arriving.
        self._page.show_thinking()

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

        # The reply is complete, so the shape-level tells can be seen and
        # removed: the "or should I distract you?" support-menu and stray
        # emoji the model adds against instructions. Rewrite the bubble only
        # when this actually changes something, so an ordinary reply — which
        # is almost all of them — never flickers. Voice is cleaned separately,
        # in clean_for_speech, since it speaks sentence by sentence.
        from brain.reply_style import humanize_reply
        humanized = humanize_reply(self._response_text)
        self._response_text = humanized
        # Always finalise the bubble: set_text does the full, syntax-highlighted
        # Markdown render (streaming only ever did the fast plain pass), and it
        # applies the humanised text whether or not the guard changed anything.
        # It gets its own words only — the whole turn's text here repeated any
        # sentence Mike said before a tool ("I'll set that up. I'll set that
        # up. Done — …").
        if self._stream_bubble is not None:
            self._stream_bubble.set_text(humanize_reply(self._bubble_text))
        self._bubble_text = ""

        # The corner streamed the raw tokens, so it still shows the pre-guard
        # text (the "or should I distract you?" menu the humaniser strips). Give
        # it the cleaned final reply too, so the companion never shows what the
        # main surface just removed.
        if (self._floating is not None and self._floating.isVisible()
                and humanized.strip()):
            self._floating.set_response(humanized)

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

        # Save Mike's final (humanised) reply and the conversation's running
        # summary, so reopening this chat restores exactly what was said and
        # the context Mike had — not a summary of some other conversation.
        if answer:
            conversation_store.add_message(self._conversation_id, "assistant", answer)
        try:
            conversation_store.set_summary(
                self._conversation_id, self._runtime.situation_summary)
        except Exception:
            logger.debug("Could not save the conversation summary.", exc_info=True)

        # A turn may have started, advanced or finished a mission.
        self._missions.refresh()

        self._stream_bubble = None
        self._action_card = None
        self._response_text = ""
        self._spoken_up_to = 0

        # Generating the text is not the same as being finished, and saying so
        # was a small lie the interface told constantly: Mike went visibly idle
        # the instant the last token arrived while he was still several
        # seconds into speaking the answer aloud. So the panel stays in
        # "speaking" for as long as there is actually a voice, and _pump_speech
        # returns it to idle when the sound stops.
        still_speaking = (
            self._speech_allowed()
            and (self._speech_pump_timer.isActive() or self._speaker.is_speaking())
        )
        self._page.set_state("speaking" if still_speaking else "idle")

        self._page.input.set_enabled(True)
        self._page.input.focus()

    def _on_error(self, error: str) -> None:

        self._page.hide_thinking()

        readable = _humanize_error(error)

        # Shown as what it is — a problem, with its fix — rather than dressed
        # up as something Mike said.
        self._add_notice(readable, "error")
        self._page.set_state("error")

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
        logger.info("Asking the user to approve: %s", (description or "").splitlines()[0][:160] if description else "")

        self._page.set_state("needs_user")
        self._page.confirm.ask(description)

    def _resolve_confirmation(self, approved: bool) -> None:

        logger.info("The user %s it.", "approved" if approved else "declined")
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

        self._add_notice(message, "info")

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

    def stop_speaking(self) -> None:
        """Silence Mike mid-answer without touching anything else."""
        if not (self._speaker.is_speaking() or self._speech_pump_timer.isActive()):
            return
        self._speaker.stop()
        self._speech_pump_timer.stop()
        self._page.input.voice.set_state("idle")
        self._wake.resume()
        if self._page.state() == "speaking":
            self._page.set_state("idle")
        if self._floating and self._floating.isVisible():
            self._floating.finish()

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

    # =====================================================
    # Conversations
    # =====================================================

    #: Reopening Mike continues the last chat only if it's this recent; after
    #: that, a new session starts fresh (the old chat stays in History).
    RESUME_WITHIN_HOURS = 12

    def _quiesce(self) -> None:
        """Stop whatever turn is running before the conversation changes.

        A cancelled worker can still append its partial reply to the runtime's
        history as it unwinds; resetting history underneath it would let that
        reply leak into the new chat. Cancellation stops the model stream within
        a chunk, so the wait is normally a fraction of a second, and it is
        bounded so a slow tool can never freeze the window.
        """
        self._speaker.stop()
        self._speech_pump_timer.stop()
        if self._worker is not None:
            self.cancel_active()
        for thread in list(self._retired_threads):
            try:
                thread.wait(2500)
            except Exception:
                pass

    def new_conversation(self) -> None:
        """Start a fresh chat: new screen, and Mike genuinely forgets the old
        one (it stays saved in the rail)."""
        self._quiesce()
        self._conversation_id = None
        self._runtime.new_conversation()
        self._page.clear()
        self._page.set_state("idle")
        self._page.input.set_enabled(True)
        self._page.input.focus()
        self._notify_conversation()

    def open_conversation(self, conversation_id: int) -> None:
        """Reopen a saved chat and continue it with the context it had."""
        convo = conversation_store.get(conversation_id)
        if convo is None:
            return
        turns = conversation_store.messages(conversation_id)
        self._quiesce()
        self._conversation_id = conversation_id
        self._runtime.restore_conversation(turns, convo.get("summary", ""))
        self._page.show_conversation(turns)
        self._page.set_state("idle")
        self._page.input.set_enabled(True)
        self._page.input.focus()
        self._notify_conversation()

    def _notify_conversation(self) -> None:
        """Let the surface mark the current chat in the rail and title it."""
        hook = getattr(self._page, "conversation_changed", None)
        if hook is None:
            return
        try:
            hook(self._conversation_id)
        except Exception:
            logger.exception("Could not update the conversation list.")

    def _add_notice(self, text: str, kind: str) -> None:
        add = getattr(self._page, "add_notice", None)
        if add is not None:
            add(text, kind)
        else:
            self._page.add_mike_message(text)

    # =====================================================
    # Missions
    # =====================================================

    def _on_mission_changed(self, mission, newly_done: list, _changes: list) -> None:
        bar = getattr(self._page, "mission", None)
        if bar is not None:
            bar.set_mission(mission, newly_done)
        if self._floating is not None and hasattr(self._floating, "set_mission"):
            self._floating.set_mission(mission, newly_done)
        if mission and mission.get("conversation_id") is None and self._conversation_id:
            from brain import mission_store
            mission_store.bind_conversation(mission["id"], self._conversation_id)

    def _drop_mission(self) -> None:
        from brain import mission_store
        mission = self._missions.current
        if not mission:
            return
        try:
            mission_store.finish(mission["id"], "dropped")
        except Exception:
            logger.exception("Could not stop tracking the mission.")
            return
        self._add_notice(f"Stopped tracking “{mission['goal']}”.", "info")
        self._missions.refresh()

    def _resume_mission(self) -> bool:
        """Open Mike into the mission you left, and say what moved since.

        Everything said here is read from the files -- no model call -- so it
        is there the instant the window is, and it is true.
        """
        from brain import mission_store
        try:
            mission = mission_store.active()
            if mission is None:
                return False
            mission = mission_store.evaluate(mission["id"])["mission"]
            changes = mission_store.changes_since_seen(mission["id"])
        except Exception:
            logger.exception("Could not resume the mission.")
            return False
        conv = mission.get("conversation_id")
        if conv and conversation_store.get(conv):
            self.open_conversation(int(conv))
        # Back within half an hour and nothing moved: just be there. A welcome
        # on every restart is the kind of thing people learn to ignore.
        ago = mission_store.seen_ago(mission["id"])
        if not changes and ago is not None and ago < 30 * 60:
            return True
        text = _welcome_back(mission, changes)
        self.mission_welcome = text
        self._page.add_mike_message(text)
        if self._conversation_id is None:
            self._conversation_id = conversation_store.create()
            mission_store.bind_conversation(mission["id"], self._conversation_id)
            self._notify_conversation()
        conversation_store.add_message(self._conversation_id, "assistant", text)
        self._runtime.note_assistant(text)
        mission_store.mark_seen(mission["id"])
        return True

    def resume_recent_conversation(self) -> None:
        import time as _time
        if self._resume_mission():
            return
        try:
            last = conversation_store.latest()
        except Exception:
            last = None
        if not last:
            return
        age_h = (_time.time() - float(last.get("updated_at") or 0)) / 3600.0
        if age_h <= self.RESUME_WITHIN_HOURS:
            self.open_conversation(int(last["id"]))
            # Opening Mike into an earlier chat should say so, rather than
            # leave someone wondering why old messages are on screen.
            if hasattr(self._page, "add_notice"):
                ago = ("a few minutes ago" if age_h < 0.25 else
                       "earlier" if age_h < 1 else
                       f"{int(age_h)} hour{'s' if int(age_h) != 1 else ''} ago")
                self._page.add_notice(
                    f"Picking up the chat from {ago}. Press Ctrl+N for a fresh one.", "info")

    @property
    def conversation_id(self) -> int | None:
        return self._conversation_id

    @property
    def wake_listening(self) -> bool:
        """Is "Hey Mike" actually being listened for right now — not just
        switched on in Settings, but running on this machine?"""
        try:
            return bool(self._wake.is_active)
        except Exception:
            return False

    def reload_voice(self) -> None:
        """A voice picked in settings — rebuild the speaker's provider so it
        takes effect immediately rather than on the next launch."""
        try:
            self._speaker.reload_provider()
        except Exception:
            logger.exception("Could not reload the voice.")

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
            (old_worker.tool_progress, self._on_tool_progress),
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
            # No turn running — but Mike may still be reading a finished
            # answer aloud. Stop / Esc should silence him too, rather than do
            # nothing while he talks on.
            self.stop_speaking()
            return

        self._retire_active_worker()

        self._speaker.stop()
        self._speech_pump_timer.stop()
        self._page.hide_thinking()

        self._stream_bubble = None
        self._action_card = None

        self._page.confirm.hide()
        mark_stopped = getattr(self._page, "mark_stopped", None)
        if mark_stopped is not None:
            mark_stopped()
        if hasattr(self._page, "add_notice"):
            self._page.add_notice("You stopped Mike. Nothing else from that request will run.",
                                  "stopped")
        else:
            self._page.add_mike_message("Cancelled.")
        self._page.set_state("idle")

        if self._floating and self._floating.isVisible():
            self._floating.set_response("Stopped.")
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

        self._missions.stop()
        # What you saw this session is "seen": next time Mike reports only
        # what moved while he was closed.
        try:
            from brain import mission_store
            mission = mission_store.active()
            if mission is not None:
                mission_store.evaluate(mission["id"])
                mission_store.mark_seen(mission["id"])
        except Exception:
            logger.debug("Could not settle the mission on quit.", exc_info=True)

        self._speaker.stop()
        self._wake.stop()

        # Cut the speech-to-text prewarm's wait short and let the thread go.
        self._prewarm_stop.set()
        if self._prewarm_thread is not None and self._prewarm_thread.is_alive():
            self._prewarm_thread.join(timeout=0.5)
        self._prewarm_thread = None

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


def _welcome_back(mission: dict, changes: list[str]) -> str:
    from brain import mission_store
    done, total = mission_store.progress(mission)
    nxt = mission_store.next_step(mission)
    due = f", due {mission['deadline']}" if mission.get("deadline") else ""
    lines = [f"Welcome back — **{mission['goal']}**{due}."]
    if changes:
        lines.append("Since last time: " + "; ".join(changes) + ".")
    elif any(f["role"] == "work" for f in mission.get("files", [])):
        lines.append("Nothing in your files has changed since last time.")
    if nxt is None:
        lines.append(f"All {total} steps are done — say the word and I'll wrap it up.")
    else:
        measure = ""
        if nxt["section"] and "words" in (nxt["evidence"] or ""):
            measure = f" ({nxt['evidence'].split(' in ')[0]} so far)"
        lines.append(f"{done} of {total} done. Next: **{nxt['title']}**{measure}.")
    if mission.get("blocker"):
        lines.append(f"Last time you were stuck on: {mission['blocker']}.")
    return "\n\n".join(lines)


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
