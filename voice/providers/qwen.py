"""Qwen3-TTS 0.6B (4-bit) as one of Mike's voices.

Three decisions shape this file, all of them made from measurement.

**It runs in a separate process.** Not for isolation theatre — for three
concrete reasons. The runtime it needs pins `transformers==5.0.0rc3`, and
Mike's own environment is certified against a passing test suite that should
not take on a release candidate. Killing a process is the fastest and most
complete way to stop speech, which is exactly what barge-in needs. And a
model that crashes takes its own process with it rather than Mike.

**The model is loaded once and kept.** Loading costs 1.2 s and 0.88 GB. A
process per utterance would pay that every sentence; a persistent worker pays
it once, at first use.

**Playback happens here, not in the worker.** The worker writes chunks and
reports paths; this side plays them with `afplay` — the same shape as the
native voice, so stopping is the same operation and the lifecycle code that
already works keeps working.

Everything about it is optional. If the worker will not start, or dies, or
falls silent, `available()` says so and the caller uses the native voice.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

from logs.logger import logger
from voice.providers.base import VoiceProvider

# The interpreter with mlx-audio installed. Deliberately not Mike's own.
DEFAULT_PYTHON = Path.home() / ".mike-tts-bench" / "bin" / "python"
DEFAULT_HF_HOME = Path.home() / ".mike-tts-bench" / "hf"

MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-4bit"

# The nine voices this model ships with, and what they actually sound like.
# Recorded here rather than left to be rediscovered: the English-native ones
# are the short list for Mike, and the rest are here so the choice is visible
# rather than hidden in a model card.
VOICES = {
    "Ryan":     "dynamic male, strong rhythmic drive (English)",
    "Aiden":    "sunny American male, clear midrange (English)",
    "Serena":   "warm, gentle young female (Chinese-native)",
    "Vivian":   "bright, slightly edgy young female (Chinese-native)",
    "Uncle_Fu": "seasoned male, low mellow timbre (Chinese-native)",
    "Dylan":    "youthful Beijing male, clear natural timbre (Chinese-native)",
    "Eric":     "lively Chengdu male, husky brightness (Chinese-native)",
    "Ono_Anna": "playful Japanese female, light nimble timbre (Japanese-native)",
    "Sohee":    "warm Korean female, rich emotion (Korean-native)",
}

# Measured: the model loads in ~1.2 s alone, slower with the brain resident.
STARTUP_TIMEOUT = 90.0

# If the worker produces nothing at all for this long after being asked to
# speak, treat it as failed and fall back rather than leaving a silence.
FIRST_CHUNK_TIMEOUT = 12.0


class QwenVoice(VoiceProvider):

    name = "qwen"
    queues = True

    def __init__(self, python: Path | None = None, model: str = MODEL,
                 voice: str | None = None, instruct: str | None = None,
                 chunk_seconds: float = 0.5) -> None:
        self._python = Path(python or os.environ.get("MIKE_QWEN_PYTHON", DEFAULT_PYTHON))
        self._model = model
        self._voice = voice or self._preference("voice_qwen_speaker", "Ryan")
        # How Mike should sound, in words. Configurable because the right
        # answer is a matter of taste rather than of engineering, and because
        # a person should be able to change it without editing code.
        self._instruct = (
            instruct if instruct is not None
            else self._preference("voice_qwen_instruct", "")
        )
        self._chunk_seconds = chunk_seconds

        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._events: queue.Queue = queue.Queue()
        self._workdir: str | None = None
        self._ready = False
        self._lock = threading.Lock()

        self._player: subprocess.Popen | None = None
        self._playback: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._request = 0
        self._last_failure = ""
        self._last_truncation = ""
        self._first_audio_ms = 0
        self._pending: list[tuple[int, str]] = []
        self._queue_lock = threading.Lock()
        self._mailboxes: dict[int, queue.Queue] = {}
        self._mailbox_lock = threading.Lock()
        # Set false by a failure, true again by a clean utterance. The caller
        # reads it to decide whether to try this voice again — a provider
        # that failed once should not be abandoned for the session, and one
        # that is failing repeatedly should not be retried every sentence.
        self._healthy = True

    @staticmethod
    def _preference(key: str, default: str) -> str:
        try:
            from config import preferences

            return str(preferences.get(key, default) or default)
        except Exception:
            return default


    # ── availability ──────────────────────────────────────

    def available(self) -> tuple[bool, str]:
        if not self._python.exists():
            return False, f"no interpreter at {self._python}"
        if shutil.which("afplay") is None:
            return False, "afplay is not on this machine"
        weights = DEFAULT_HF_HOME / "hub" / f"models--{self._model.replace('/', '--')}"
        if not weights.exists():
            return False, f"model weights are not downloaded ({self._model})"
        if self._voice not in VOICES:
            return False, (f"unknown voice {self._voice!r}; this model has: "
                           + ", ".join(sorted(VOICES)))
        return True, f"Qwen3-TTS 4-bit ({self._voice})"

    # ── the worker ────────────────────────────────────────

    def warm_up(self) -> None:
        self._ensure_worker()

    def _ensure_worker(self) -> bool:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None and self._ready:
                return True
            if self._proc is not None:
                self._kill_worker()

            env = dict(os.environ)
            env["HF_HOME"] = str(DEFAULT_HF_HOME)
            env["MIKE_QWEN_TTS_MODEL"] = self._model
            env["MIKE_QWEN_TTS_VOICE"] = self._voice
            env["MIKE_QWEN_TTS_INSTRUCT"] = self._instruct
            env["MIKE_QWEN_TTS_CHUNK"] = str(self._chunk_seconds)
            worker = Path(__file__).parent / "qwen_worker.py"

            try:
                self._proc = subprocess.Popen(
                    [str(self._python), str(worker)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env,
                )
            except Exception as exc:
                self._last_failure = f"worker would not start: {exc}"
                logger.warning("Qwen TTS %s", self._last_failure)
                return False

            self._events = queue.Queue()
            self._reader = threading.Thread(target=self._read_events, daemon=True)
            self._reader.start()

            started = time.monotonic()
            while time.monotonic() - started < STARTUP_TIMEOUT:
                try:
                    event = self._events.get(timeout=0.5)
                except queue.Empty:
                    if self._proc.poll() is not None:
                        self._last_failure = "worker exited during startup"
                        return False
                    continue
                if event.get("event") == "ready":
                    self._workdir = event.get("workdir")
                    self._ready = True
                    logger.info("Qwen TTS ready (%s, voice %s)", self._model, self._voice)
                    return True
                if event.get("event") == "fatal":
                    self._last_failure = str(event.get("error"))[:200]
                    logger.warning("Qwen TTS failed to start: %s", self._last_failure)
                    self._kill_worker()
                    return False

            self._last_failure = "worker did not become ready in time"
            self._kill_worker()
            return False

    def _read_events(self) -> None:
        """Sort worker events into a mailbox per request.

        The first version put everything in one queue and had the playback
        loop skip anything not addressed to the utterance it was playing.
        That works only while generation never runs ahead of playback — and
        the whole point of queueing is that it does. Chunks for the next
        sentence arrived mid-playback, matched nothing, and were dropped;
        the next sentence then waited for audio that had already been thrown
        away. Nothing errored. It just took three times longer than it should.
        """
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._deliver(event)

    def _deliver(self, event: dict) -> None:
        request_id = event.get("id")
        if request_id is None:
            self._events.put(event)          # startup events: ready, fatal
            return
        with self._mailbox_lock:
            box = self._mailboxes.get(request_id)
            if box is None:
                box = queue.Queue()
                self._mailboxes[request_id] = box
        box.put(event)

    def _mailbox(self, request_id: int) -> queue.Queue:
        with self._mailbox_lock:
            box = self._mailboxes.get(request_id)
            if box is None:
                box = queue.Queue()
                self._mailboxes[request_id] = box
            return box

    def _close_mailbox(self, request_id: int) -> None:
        with self._mailbox_lock:
            self._mailboxes.pop(request_id, None)

    def _kill_worker(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.kill()
            self._proc.wait(timeout=2)
        except Exception:
            pass
        self._proc = None
        self._ready = False
        if self._workdir:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None

    # ── speaking ──────────────────────────────────────────

    def speak(self, text: str) -> bool:
        """Hand the utterance to the worker and return immediately.

        Nothing is waited for here. Generating the first chunk takes about
        240 ms, and this is called from the UI thread once per sentence of a
        streaming reply, so waiting froze the interface for a quarter second
        every sentence. The wait now happens on the playback thread, where
        it costs nobody anything.
        """
        if not text or not text.strip():
            return False
        self.stop()
        if not self._ensure_worker():
            return False

        self._stop_flag.clear()
        self._last_truncation = ""
        return self._submit(text)

    def enqueue(self, text: str) -> bool:
        """Add an utterance without cutting off the one being spoken.

        This is what makes a multi-sentence reply flow. The worker generates
        the next sentence while the parent is still playing the previous one,
        so generation and playback overlap instead of taking turns. Without
        it a five-sentence reply pays the generation cost of every sentence
        in series, which measured three times slower end to end than the
        system voice even though the speech itself is only 40% longer.
        """
        if not text or not text.strip():
            return False
        if not self._ensure_worker():
            return False
        self._stop_flag.clear()
        return self._submit(text)

    def _submit(self, text: str) -> bool:
        self._request += 1
        request_id = self._request
        try:
            assert self._proc is not None and self._proc.stdin is not None
            self._proc.stdin.write(
                json.dumps({"cmd": "speak", "text": text, "id": request_id}) + "\n")
            self._proc.stdin.flush()
        except Exception as exc:
            self._last_failure = f"could not reach the worker: {exc}"
            logger.warning("Qwen TTS %s", self._last_failure)
            self._kill_worker()
            return False
        with self._queue_lock:
            self._pending.append((request_id, text))
        self._ensure_playback_thread()
        return True

    def _ensure_playback_thread(self) -> None:
        with self._queue_lock:
            alive = self._playback is not None and self._playback.is_alive()
            if alive:
                return
            self._playback = threading.Thread(target=self._drain, daemon=True)
            self._playback.start()

    def _drain(self) -> None:
        """Play queued utterances in order until the queue empties."""
        while not self._stop_flag.is_set():
            with self._queue_lock:
                if not self._pending:
                    return
                request_id, text = self._pending.pop(0)
            self._await_and_play(request_id, text)

    def _await_and_play(self, request_id: int, text: str) -> None:
        """Wait for the first chunk, then play the rest as it arrives.

        Runs off the caller's thread. If no audio ever arrives, the utterance
        is handed back through on_failure so another voice can say it — the
        caller is long gone by then and cannot be told any other way.
        """
        started = time.monotonic()
        first: dict | None = None
        box = self._mailbox(request_id)

        while time.monotonic() - started < FIRST_CHUNK_TIMEOUT:
            if self._stop_flag.is_set():
                self._close_mailbox(request_id)
                return
            try:
                event = box.get(timeout=0.2)
            except queue.Empty:
                if self._proc is None or self._proc.poll() is not None:
                    self._fail(text, "the worker died while generating")
                    self._close_mailbox(request_id)
                    return
                continue
            kind = event.get("event")
            if kind == "audio":
                first = event
                break
            if kind in ("error", "fatal"):
                self._fail(text, str(event.get("error"))[:200])
                self._close_mailbox(request_id)
                return
            if kind in ("done", "truncated", "timeout"):
                self._fail(text, f"the worker returned {kind} with no audio")
                self._close_mailbox(request_id)
                return

        if first is None:
            self._fail(text, "no audio within the first-chunk timeout")
            self._close_mailbox(request_id)
            return

        self._first_audio_ms = round((time.monotonic() - started) * 1000)
        self._play_stream(request_id, first)

    def _fail(self, text: str, reason: str) -> None:
        """Record a failure and hand the words to whoever can say them."""
        self._last_failure = reason
        self._healthy = False
        logger.warning("Qwen TTS could not speak (%s)", reason)
        handler = self.on_failure
        if handler and not self._stop_flag.is_set():
            try:
                handler(text, reason)
            except Exception:
                logger.exception("Voice fallback failed.")

    def _play_stream(self, request_id: int, first: dict) -> None:
        """Play the utterance, coalescing chunks into as few files as possible.

        The obvious implementation — one `afplay` per chunk as it arrives —
        is measurably wrong. At half-second chunks a four-second sentence
        becomes eight process spawns, and the gap at every seam turned four
        seconds of speech into thirteen seconds of stuttering delivery.

        So the first chunk plays immediately, because that is what makes Mike
        start talking quickly, and everything generated while it plays is
        concatenated into a single file and played as one. Generation runs
        faster than real time, so in practice a sentence is two files: the
        opening half-second, and the rest.
        """
        box = self._mailbox(request_id)
        buffered: list[str] = []
        finished = False

        self._play_file(first.get("path"))

        while not self._stop_flag.is_set():
            # Drain whatever the worker has produced so far without waiting.
            while True:
                try:
                    event = box.get_nowait()
                except queue.Empty:
                    break
                kind = event.get("event")
                if kind == "audio":
                    buffered.append(event.get("path"))
                elif kind in ("truncated", "timeout"):
                    self._last_truncation = (
                        f"{kind} at {event.get('seconds')}s "
                        f"(ceiling {event.get('limit')}s)"
                    )
                    self._healthy = False
                    logger.warning("Qwen TTS %s — runaway generation stopped",
                                   self._last_truncation)
                    finished = True
                elif kind == "done":
                    self._healthy = True
                    finished = True
                elif kind == "error":
                    self._healthy = False
                    finished = True

            if buffered:
                self._play_file(self._join(buffered))
                buffered = []
                continue
            if finished:
                break
            if self._proc is None or self._proc.poll() is not None:
                break
            time.sleep(0.02)

        self._close_mailbox(request_id)

    @staticmethod
    def _join(paths: list[str]) -> str | None:
        """Concatenate consecutive chunks into one playable file."""
        paths = [p for p in paths if p and os.path.exists(p)]
        if not paths:
            return None
        if len(paths) == 1:
            return paths[0]

        import wave

        target = paths[0] + ".joined.wav"
        try:
            with wave.open(paths[0]) as first:
                params = first.getparams()
            with wave.open(target, "wb") as out:
                out.setparams(params)
                for path in paths:
                    with wave.open(path) as part:
                        out.writeframes(part.readframes(part.getnframes()))
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
            return target
        except Exception as exc:
            logger.warning("Qwen TTS could not join audio chunks: %s", exc)
            return paths[0]

    def _play_file(self, path: str | None) -> None:
        """Play one file, watching for a stop the whole time it plays."""
        if not path or self._stop_flag.is_set():
            return
        try:
            self._player = subprocess.Popen(
                ["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while self._player.poll() is None:
                if self._stop_flag.is_set():
                    return
                time.sleep(0.01)
        except Exception as exc:
            logger.warning("Qwen TTS playback failed: %s", exc)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def is_speaking(self) -> bool:
        # Once stopping has been asked for, nothing is audible — even though
        # the playback thread takes a few milliseconds to notice and unwind.
        # Reporting "still speaking" there made stop() look like it had not
        # worked, and would have had the caller stopping twice.
        if self._stop_flag.is_set():
            return False
        if self._player is not None and self._player.poll() is None:
            return True
        with self._queue_lock:
            if self._pending:
                return True
        return bool(self._playback is not None and self._playback.is_alive())

    def stop(self) -> None:
        self._stop_flag.set()
        # Anything queued behind the current utterance is part of the reply
        # the user just interrupted, so it goes with it. Leaving it would
        # have Mike resume talking after being told to stop.
        with self._queue_lock:
            self._pending.clear()
        with self._mailbox_lock:
            self._mailboxes.clear()
        player = self._player
        if player is not None:
            try:
                player.terminate()
                player.wait(timeout=1)
            except Exception:
                try:
                    player.kill()
                except Exception:
                    pass
        self._player = None
        # Drain anything the worker is still reporting for the abandoned
        # utterance, so the next one does not read stale events.
        while True:
            try:
                self._events.get_nowait()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        self.stop()
        if self._proc is not None and self._proc.poll() is None:
            try:
                assert self._proc.stdin is not None
                self._proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=2)
            except Exception:
                pass
        self._kill_worker()

    # ── reporting ─────────────────────────────────────────

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def first_audio_ms(self) -> int:
        """How long the last utterance took to become audible."""
        return self._first_audio_ms

    @property
    def last_failure(self) -> str:
        return self._last_failure

    @property
    def last_truncation(self) -> str:
        return self._last_truncation
