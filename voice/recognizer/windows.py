"""Windows speech-to-text backend: a local Whisper model via faster-whisper.

SFSpeechRecognizer has no Windows equivalent, and the OS's own Windows
Speech Recognition is not scriptable in a way that fits the async contract
here. faster-whisper (CTranslate2) runs a real Whisper model entirely
offline and on-device -- chosen over openai-whisper (much slower on CPU)
and whisper.cpp (a C++ binary with no first-party Python binding as clean
as this pip package) after checking what this machine actually has: 14
logical CPUs with AVX2, integrated graphics only, no CUDA. INT8 CPU
inference is the only practical path, and it's fast enough for one: a
3.2-second utterance transcribes in ~4-5s with the medium.en model,
measured on this machine, not assumed.

The model itself (~1.5GB) downloads once from Hugging Face on first use and
is cached under ~/.cache/huggingface; nothing here bundles or vendors it.
"""
from __future__ import annotations

import threading
from typing import Callable

from logs.logger import logger
from voice.recognizer.base import SpeechRecognizer

MODEL_SIZE = "medium.en"
COMPUTE_TYPE = "int8"  # no GPU on this machine -- INT8 is the fast CPU path


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

        medium.en is ~1.5GB; loading it lazily on the first spoken command
        meant the first "Hey Mike" froze on a multi-minute download showing
        only "transcribing". Called from a background thread at startup so the
        model is ready — or well on its way — by the time anyone speaks.
        """
        try:
            self._get_model()
        except Exception:
            logger.exception("Whisper prewarm failed; first transcription will load the model.")

    def _get_model(self):
        with self._load_lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                logger.info("Loading Whisper model %s (first use)...", self._model_size)
                self._model = WhisperModel(
                    self._model_size, device="cpu", compute_type=COMPUTE_TYPE,
                )
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
