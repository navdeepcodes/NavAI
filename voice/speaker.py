"""Mike's speaking voice.

This used to *be* the macOS `say` command. It now drives a VoiceProvider, so
which voice Mike speaks in is a choice rather than an assumption baked into
every call site. The queueing, sentence-splitting and streaming behaviour
above it is unchanged, because that logic was never about `say`.

The fallback rule is the important part. A neural voice can fail in ways the
system voice cannot — a worker that will not start, a model that produces
nothing, a generation that runs away. Whenever that happens the utterance is
handed to the native voice and Mike finishes the sentence. Mike never goes
silent because the good voice broke.
"""
from __future__ import annotations

import re
import time

from logs.logger import logger
from voice import diagnostics
from voice.providers import VoiceProvider, get_provider
from voice.providers.native import NativeVoice

VOICE = "Samantha"
RATE = 185


_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


class Speaker:

    def __init__(self, provider: VoiceProvider | None = None) -> None:
        self._queue: list[str] = []
        self._streaming = False
        # The native voice is held separately from the configured one: it is
        # the fallback, so it must exist even when it is not the default.
        self._native = NativeVoice()
        self._provider = provider or self._configured_provider(self._native)
        self._fell_back = False
        # An accepted utterance can still fail, and by then the caller has
        # moved on. The provider hands the words back here so the native
        # voice can say them — the user hears one continuous reply and never
        # learns which engine produced which sentence.
        self._provider.on_failure = self._recover
        self._consecutive_failures = 0
        self._record: diagnostics.Utterance | None = None

    @staticmethod
    def _configured_provider(native: NativeVoice) -> VoiceProvider:
        """The configured voice, reusing the fallback instance when they are
        the same thing.

        Returning a second NativeVoice when native is the configured choice
        left Mike holding two of them. Behaviour survived it — stop() stops
        both — but one voice should be one object, and the duplicate made
        "which one is actually speaking?" ambiguous.
        """
        try:
            from config import preferences

            choice = str(preferences.get("voice_provider", "native") or "native")
        except Exception:
            return native

        if choice.strip().lower() in ("", "native", "macos", "say", "samantha"):
            return native
        provider = get_provider(choice)
        return native if provider.name == "native" else provider

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def fell_back(self) -> bool:
        """True if the configured voice failed and the native one covered."""
        return self._fell_back

    # After this many failures in a row the configured voice is left alone
    # for the rest of the reply. Retrying a sick worker once per sentence
    # turns one failure into a stutter of failures, each costing its own
    # timeout before the native voice gets a turn.
    _GIVE_UP_AFTER = 2

    def _say(self, text: str) -> None:
        """Speak through the configured provider, falling back if it cannot."""
        self._record = diagnostics.begin(self._provider.name, text)
        if self._provider is not self._native and self._usable():
            if self._provider.speak(text):
                return
            self._note_failure(getattr(self._provider, "last_failure", "refused"))
        if self._provider is not self._native:
            self._record.fell_back_to = self._native.name
        self._native.speak(text)

    def _usable(self) -> bool:
        healthy = getattr(self._provider, "healthy", True)
        return healthy and self._consecutive_failures < self._GIVE_UP_AFTER

    def _note_failure(self, reason: str) -> None:
        if self._record is not None:
            self._record.failure = reason[:160]
        self._fell_back = True
        self._consecutive_failures += 1
        logger.warning(
            "Voice provider %r could not speak (%s); using the native voice"
            " [%d in a row].",
            self._provider.name, reason, self._consecutive_failures,
        )

    def _recover(self, text: str, reason: str) -> None:  # noqa: D401
        """Finish an utterance the configured voice accepted and then dropped.

        Called from the provider's own thread. Speaks rather than queues,
        because this is a sentence the user is currently waiting to hear.
        """
        self._note_failure(reason)
        if self._record is not None:
            self._record.fell_back_to = self._native.name
        self._native.speak(text)

    def reset_health(self) -> None:
        """Give the configured voice another chance.

        Called at the start of a turn rather than continuously: one bad reply
        should not disable the voice for the session, and a failing worker
        should not be retried in the middle of the reply it is failing.
        """
        self._consecutive_failures = 0

    def speak(self, text: str) -> None:
        if not text or not text.strip():
            return
        self.stop()
        clean = clean_for_speech(text)
        if not clean:
            return
        logger.info("Speaking (%s): %s", self._provider.name, clean[:80])
        self._say(clean)

    def speak_sentence(self, sentence: str) -> None:
        clean = clean_for_speech(sentence)
        if not clean:
            return
        self._queue.append(clean)
        self._streaming = True
        # Hand it over immediately if the voice can hold a queue: that lets
        # the next sentence generate while this one plays. Voices that cannot
        # queue are paced by pump() instead, exactly as before.
        if getattr(self._provider, "queues", False) and self._usable():
            self._drain_to_provider()
        elif not self.is_speaking():
            self._speak_next()

    def _drain_to_provider(self) -> None:
        while self._queue:
            text = self._queue.pop(0)
            self._record = diagnostics.begin(self._provider.name, text)
            if not (self._usable() and self._provider.enqueue(text)):
                self._note_failure(
                    getattr(self._provider, "last_failure", "refused"))
                self._record.fell_back_to = self._native.name
                self._queue.insert(0, text)
                self._speak_next()
                return

    def finish_streaming(self) -> None:
        self._streaming = False

    def _speak_next(self) -> None:
        if not self._queue:
            return
        text = self._queue.pop(0)
        logger.info("Speaking chunk (%s): %s", self._provider.name, text[:60])
        self._say(text)

    def pump(self) -> None:
        if self.is_speaking():
            return
        if self._queue:
            self._speak_next()

    @property
    def streaming_done(self) -> bool:
        return not self._streaming or (not self._queue and not self.is_speaking())

    def stop(self) -> None:
        self._queue.clear()
        self._streaming = False
        # Both, always. After a fallback the native voice may be the one
        # making noise even though the configured provider is the Qwen one,
        # and stopping only the configured provider would leave it talking.
        if self._record is not None and self._record.finished_after_ms is None:
            if self.is_speaking():
                self._record.interrupted = True
            self._record.finished_after_ms = round(
                (time.time() - self._record.started_at) * 1000)
            first = getattr(self._provider, "first_audio_ms", 0)
            if first and self._record.first_audio_ms is None:
                self._record.first_audio_ms = first
            truncation = getattr(self._provider, "last_truncation", "")
            if truncation:
                self._record.truncated = truncation
        self._provider.stop()
        if self._provider is not self._native:
            self._native.stop()

    def is_speaking(self) -> bool:
        return self._provider.is_speaking() or (
            self._provider is not self._native and self._native.is_speaking()
        )

    def shutdown(self) -> None:
        """Release the provider. Called from the app's teardown path."""
        try:
            self._provider.shutdown()
        except Exception:
            logger.exception("Voice provider shutdown failed.")
        if self._provider is not self._native:
            self._native.stop()


_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended
    "\U00002600-\U000026FF"  # misc symbols
    "\U0000200D"             # zero width joiner
    "\U00002B50"             # star
    "\U0000203C-\U00003299"  # misc
    "]+",
    flags=re.UNICODE,
)

_URL_RE = re.compile(
    r'https?://[^\s\)\]>\"\']+',
    re.IGNORECASE,
)

_PATH_RE = re.compile(
    r'(?:~/|/Users/|/home/)[^\s\)\]>\"\']+',
)


def _humanize_url(url: str) -> str:
    """Turn a URL into something speakable."""
    domain = url.split("//")[-1].split("/")[0].split("?")[0]
    domain = domain.replace("www.", "")
    known = {
        "youtube.com": "YouTube",
        "google.com": "Google",
        "github.com": "GitHub",
        "stackoverflow.com": "Stack Overflow",
        "reddit.com": "Reddit",
        "twitter.com": "Twitter",
        "x.com": "X",
        "wikipedia.org": "Wikipedia",
    }
    for pattern, name in known.items():
        if pattern in domain:
            return name
    return domain


def _humanize_path(path: str) -> str:
    """Turn a file path into something speakable."""
    p = path.rstrip("/")
    p = re.sub(r'^~/', '', p)
    p = re.sub(r'^/Users/[^/]+/', '', p)
    p = re.sub(r'^/home/[^/]+/', '', p)
    parts = p.split("/")
    if len(parts) > 3:
        parts = parts[-2:]
    return " ".join(parts)


def clean_for_speech(text: str) -> str:
    """Transform UI text into natural spoken text."""
    t = text.strip()

    # Remove code blocks entirely, replace with spoken note
    has_code = bool(re.search(r'```[\s\S]*?```', t))
    t = re.sub(r'```[\s\S]*?```', ' ', t)
    if has_code:
        t = t.rstrip()
        if t and not t.endswith((".", "!", "?")):
            t += "."
        t += " I've included the code in the chat."

    # Inline code: keep the text, drop backticks
    t = re.sub(r'`([^`]+)`', r'\1', t)

    # URLs -> human-readable
    t = _URL_RE.sub(lambda m: _humanize_url(m.group(0)), t)

    # File paths -> human-readable
    t = _PATH_RE.sub(lambda m: _humanize_path(m.group(0)), t)

    # Markdown bold/italic
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]+)\*', r'\1', t)
    t = re.sub(r'__([^_]+)__', r'\1', t)
    t = re.sub(r'_([^_]+)_', r'\1', t)

    # Markdown headings
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.MULTILINE)

    # Markdown list markers
    t = re.sub(r'^\s*[-*+]\s+', '', t, flags=re.MULTILINE)
    t = re.sub(r'^\s*\d+\.\s+', '', t, flags=re.MULTILINE)

    # Markdown links
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)

    # Markdown horizontal rules
    t = re.sub(r'^[-*_]{3,}\s*$', '', t, flags=re.MULTILINE)

    # Symbols that sound bad (before emoji strip, since some overlap)
    t = t.replace('→', ' to ')
    t = t.replace('←', ' from ')
    t = t.replace('↓', '')
    t = t.replace('↑', '')
    t = t.replace('•••', '')
    t = t.replace('•', ',')
    t = t.replace('…', '...')
    t = t.replace('|', ',')
    t = t.replace('✓', '')
    t = t.replace('✗', '')
    t = t.replace('✅', '')
    t = t.replace('❌', '')
    t = re.sub(r'[{}<>]', '', t)

    # Emojis (after symbol replacements)
    t = _EMOJI_RE.sub('', t)

    # Clean up spacing and punctuation
    t = re.sub(r'\n{2,}', '. ', t)
    t = re.sub(r'\n', ' ', t)
    t = re.sub(r'\.{2,}', '.', t)
    t = re.sub(r'\.\s*\.', '.', t)
    t = re.sub(r',\s*,', ',', t)
    t = re.sub(r'\s{2,}', ' ', t)
    t = re.sub(r'^\s*[.,]\s*', '', t)

    t = _add_conversational_pauses(t)

    return t.strip()


def _add_conversational_pauses(text: str) -> str:
    """Insert natural breathing pauses using macOS say inline commands."""
    # Pause after sentence-ending punctuation
    text = re.sub(r'([.!?])\s+', r'\1 [[slnc 180]] ', text)

    # Shorter pause after commas
    text = re.sub(r',\s+', r', [[slnc 80]] ', text)

    # Pause after colons and semicolons
    text = re.sub(r'([;:])\s+', r'\1 [[slnc 120]] ', text)

    # Pause after dashes used as breaks
    text = re.sub(r'\s+—\s+', ' [[slnc 100]] ', text)
    text = re.sub(r'\s+--\s+', ' [[slnc 100]] ', text)

    return text
