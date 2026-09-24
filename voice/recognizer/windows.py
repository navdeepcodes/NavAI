"""Windows speech-to-text backend: a local Whisper model via faster-whisper.

SFSpeechRecognizer has no Windows equivalent, and the OS's own Windows
Speech Recognition is not scriptable in a way that fits the async contract
here. faster-whisper (CTranslate2) runs a real Whisper model entirely
offline and on-device -- chosen over openai-whisper (much slower on CPU)
and whisper.cpp (a C++ binary with no first-party Python binding as clean
as this pip package) after checking what this machine actually has: 14
logical CPUs with AVX2, integrated graphics only, no CUDA. INT8 CPU
inference is the only practical path; see MODEL_SIZE for the measured
choice of model.

The model downloads once from Hugging Face on first use (small.en is ~0.5GB)
and is cached under ~/.cache/huggingface; nothing here bundles or vendors it.
"""
from __future__ import annotations

import threading
from typing import Callable

from logs.logger import logger
from voice.recognizer.base import SpeechRecognizer

#: small.en, not medium.en — measured on the target laptop (Core Ultra 5,
#: 15GB, with the 9B chat model resident, as in real use), five spoken student
#: commands with mild mic noise:
#:
#:     model      memory added   time to transcribe   real mistakes
#:     medium.en     +4.2 GB          7.7 s              1 ("lofi")
#:     small.en      +2.2 GB          2.1 s (4 threads)  1 ("lofi")
#:     base.en       +1.0 GB          0.7 s              1 ("desktop" -> "desk cup")
#:
#: medium bought no accuracy over small, cost 2GB more, and made a student
#: wait ~8s after speaking before Mike even began to think. With the chat model
#: holding 6.3GB of a 15GB machine it was also what exhausted memory: its load
#: failed outright ("mkl_malloc: failed to allocate memory") and the pressure
#: slowed every reply. base.en is the fallback when even small.en can't fit.
MODEL_SIZE = "small.en"
FALLBACK_MODEL_SIZES = ("base.en",)
COMPUTE_TYPE = "int8"  # no GPU on this machine -- INT8 is the fast CPU path
#: Transcription shares the CPU with the chat model; four threads was faster
#: (2.1s vs 2.9s for all cores) because it stops fighting the LLM for them.
CPU_THREADS = 4


class WhisperRecognizer(SpeechRecognizer):
    """Local Whisper transcription via faster-whisper, CPU-only.

    The model loads lazily, on first transcribe rather than at construction:
    get_recognizer() builds this well before the user has necessarily asked
    to speak, and a ~5s (cached) to several-minute (first download) load
    should never be a tax on Mike's startup. available() only checks that
    the package is importable -- forcing a full model load just to answer
    "can you transcribe" would make every capability check pay for one.
    """

    name = "whisper"

    def __init__(self, model_size: str = MODEL_SIZE) -> None:
        self._model_size = model_size
        self._model = None
        self._load_lock = threading.Lock()

    def available(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except Exception as exc:
            return False, f"faster-whisper is not installed ({exc})"
        return True, f"local Whisper ({self._model_size}, CPU)"

    def prewarm(self) -> None:
        """Load (downloading on first ever run) the model now.

        Loading lazily on the first spoken command meant the first "Hey
        Mike" froze on the model download showing only "transcribing".
        Called from a background thread at startup so the model is ready —
        or well on its way — by the time anyone speaks.
        """
        try:
            self._get_model()
        except Exception:
            logger.exception("Whisper prewarm failed; first transcription will load the model.")

    def _get_model(self):
        with self._load_lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                # Try the chosen model, then smaller ones. A machine too short
                # on memory for small.en should still be able to hear the user
                # with base.en, not lose voice input entirely because one
                # allocation failed.
                sizes = [self._model_size] + [
                    s for s in FALLBACK_MODEL_SIZES if s != self._model_size]
                last_error: Exception | None = None
                for size in sizes:
                    try:
                        logger.info("Loading Whisper model %s (first use)...", size)
                        self._model = WhisperModel(
                            size, device="cpu", compute_type=COMPUTE_TYPE,
                            cpu_threads=CPU_THREADS,
                        )
                        if size != self._model_size:
                            logger.warning(
                                "Whisper %s could not load (%s); using %s instead.",
                                self._model_size, last_error, size)
                        break
                    except (MemoryError, RuntimeError) as exc:
                        last_error = exc
                        logger.warning("Whisper %s failed to load: %s", size, exc)
                if self._model is None:
                    raise RuntimeError(f"No speech model could be loaded: {last_error}")
            return self._model

    def transcribe_async(
        self,
        audio_path: str,
        on_done: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Runs the (blocking) transcription on a background thread.

        on_done/on_error therefore fire from that thread, not the caller's --
        the same contract voice/recognizer/base.py documents and the macOS
        backend already has (SFSpeechRecognizer's own completion handler
        fires off-thread too). voice_input.py's Qt signals marshal safely
        back to the GUI thread regardless of which thread emits them.
        """
        def _run() -> None:
            try:
                model = self._get_model()
                segments, _info = model.transcribe(audio_path, beam_size=1)
                text = " ".join(segment.text.strip() for segment in segments).strip()
                on_done(text)
            except Exception as exc:
                logger.exception("Whisper transcription failed.")
                on_error(str(exc))

        threading.Thread(target=_run, name="whisper-transcribe", daemon=True).start()
