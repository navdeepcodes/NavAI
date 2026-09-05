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

    @abstractmethod
    def speak(self, text: str) -> bool:
        """Begin speaking `text`, replacing anything already being said.

        Returns as soon as audio is under way — never after it finishes.
        False means nothing was said and the caller should fall back.
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

    def supports_streaming(self) -> bool:
        return False

    def warm_up(self) -> None:
        """Do any expensive one-off work now rather than mid-conversation."""
