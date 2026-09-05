"""What Mike needs from a voice, independent of who produces it.

Mike had one voice implementation and it was the macOS `say` binary, which
shaped the code around it: speak() spawned a process, stop() killed it,
is_speaking() polled it. That worked, and it hid an assumption — that
producing speech is something an operating system does for you, instantly and
for free.

A neural voice is not that. It loads weights, it generates in chunks, it can
run away, and it can fail in ways `say` cannot. So the contract is written
here explicitly, and both implementations are held to it:

  * speaking never blocks the caller
  * stopping is immediate and leaves nothing running
  * a failure is reported, not raised into the agent loop
  * nothing outlives shutdown

Anything that cannot meet that contract does not belong behind this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class VoiceProvider(ABC):
    """One way of turning text into audible speech."""

    #: Shown in logs and settings. Stable, lowercase, no spaces.
    name: str = "unnamed"

    @abstractmethod
    def available(self) -> tuple[bool, str]:
        """Can this provider speak right now, and if not, why not?

        Checked before use rather than discovered mid-sentence, so the caller
        can fall back before the user notices a silence.
        """

    #: Called from a background thread when an utterance that was accepted
    #: turns out to be unspeakable. The caller sets this to route the text to
    #: a voice that works. Signature: (text, reason) -> None.
    on_failure = None

    @abstractmethod
    def speak(self, text: str) -> bool:
        """Begin speaking `text`, replacing anything already being said.

        **Must not block.** This is called from the UI thread as each sentence
        of a streaming reply becomes available, and anything it waits for is
        time the interface is frozen. Measured on the first version of the
        neural provider: 233-294 ms of stall per sentence, against 2-5 ms for
        the system voice, because it waited for the first audio chunk before
        returning.

        False means the text was refused outright and the caller should speak
        it another way. True means it was accepted — which is not the same as
        spoken. An accepted utterance that later fails reports it through
        `on_failure`, because by then the caller has moved on.
        """

    @abstractmethod
    def is_speaking(self) -> bool:
        """Is audio audible right now?"""

    @abstractmethod
    def stop(self) -> None:
        """Silence immediately and discard anything queued.

        Must be safe to call when nothing is speaking, and must leave no
        process, thread or file behind.
        """

    def shutdown(self) -> None:
        """Release everything held. Called once, at quit."""
        self.stop()

    # ── optional, for providers that can start before they finish ──

    #: True only for providers that can hold several utterances and play them
    #: in order. Declared rather than inferred: the first version of this
    #: checked whether enqueue() had been overridden, which quietly counted
    #: the system voice as a queueing provider because it overrides the method
    #: to *refuse* queueing. A capability should say what it is.
    queues = False

    def enqueue(self, text: str) -> bool:
        """Add an utterance behind whatever is already speaking.

        The default is to replace, because a provider that cannot queue is
        still correct if it simply speaks the newest thing. A provider that
        *can* queue should override this: a reply arrives sentence by
        sentence, and generating each one only after the previous has finished
        playing serialises two things that could overlap. Measured on the
        neural provider, that serialisation made a five-sentence reply take
        three times as long to deliver as the system voice, despite the speech
        itself being only about 40% longer.
        """
        return self.speak(text)

    def supports_streaming(self) -> bool:
        return False

    def warm_up(self) -> None:
        """Do any expensive one-off work now rather than mid-conversation."""
