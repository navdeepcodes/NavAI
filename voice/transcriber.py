"""Speech-to-text.

macOS uses SFSpeechRecognizer (on-device). Linux has no equivalent
preinstalled with the OS — there's no offline STT engine bundled here, and
faking one by silently no-oping would produce a worse experience than
telling the caller plainly that transcription isn't available yet. Both
entry points keep macOS's callback-based signature so voice/voice_input.py
doesn't need to know which platform it's running on.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from hostplatform import is_macos
from logs.logger import logger

_recognizer = None


def _get_recognizer():
    global _recognizer
    import Speech

    if _recognizer is None or not _recognizer.isAvailable():
        _recognizer = Speech.SFSpeechRecognizer.alloc().init()
    return _recognizer


def transcribe_blocking(audio_path: str, timeout: float = 15.0) -> str:
    """Transcribe a WAV file, blocking with run-loop spinning.

    Use from main thread in scripts (not inside Qt event loop).
    """
    if not is_macos():
        logger.warning("Speech-to-text is not implemented on this platform yet.")
        return ""

    from Foundation import NSRunLoop, NSDate

    result_holder = {"text": "", "done": False}

    def on_done(text: str):
        result_holder["text"] = text
        result_holder["done"] = True

    def on_error(msg: str):
        result_holder["done"] = True

    _start_recognition(audio_path, on_done, on_error)

    deadline = time.monotonic() + timeout
    loop = NSRunLoop.currentRunLoop()
    while not result_holder["done"] and time.monotonic() < deadline:
        loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

    if not result_holder["done"]:
        logger.warning("Transcription timed out after %.1fs", timeout)

    return result_holder["text"]


def transcribe_async(
    audio_path: str,
    on_done: Callable[[str], None],
    on_error: Callable[[str], None],
) -> None:
    """Start transcription; callbacks fire on the main thread via the run loop.

    Use from main thread inside Qt event loop (PySide6).
    """
    if not is_macos():
        on_error(
            "Speech-to-text isn't available on this platform yet — "
            "type your message instead."
        )
        return

    _start_recognition(audio_path, on_done, on_error)


def _start_recognition(
    audio_path: str,
    on_done: Callable[[str], None],
    on_error: Callable[[str], None],
) -> None:
    from Foundation import NSURL
    import Speech

    recognizer = _get_recognizer()
    if not recognizer or not recognizer.isAvailable():
        logger.error("SFSpeechRecognizer not available")
        on_error("Speech recognition is not available on this Mac.")
        return

    file_path = Path(audio_path).expanduser().resolve()
    if not file_path.exists():
        logger.error("Audio file not found: %s", file_path)
        on_error(f"Audio file not found: {file_path}")
        return

    file_url = NSURL.fileURLWithPath_(str(file_path))
    request = Speech.SFSpeechURLRecognitionRequest.alloc().initWithURL_(
        file_url
    )

    request.setShouldReportPartialResults_(False)
    request.setTaskHint_(1)  # SFSpeechRecognitionTaskHint.dictation

    request.setContextualStrings_([
        "YouTube", "Google", "GitHub", "Reddit", "Twitter",
        "Wikipedia", "Stack Overflow", "LinkedIn", "Instagram",
        "Spotify", "Netflix", "Discord", "Slack", "WhatsApp",
        "Chrome", "Safari", "Firefox", "Opera", "VS Code",
        "Ollama", "Python", "JavaScript", "TypeScript",
        "Mike", "Hey Mike", "Navdeep",
        "Gmail", "Outlook", "Figma", "Notion", "Trello",
        "ChatGPT", "Claude", "Gemini",
        "Xcode", "Terminal", "Finder",
        "Desktop", "Documents", "Downloads",
    ])

    called = {"done": False}

    def handler(result, error):
        if called["done"]:
            return
        if error is not None:
            called["done"] = True
            desc = error.localizedDescription()
            logger.error("Transcription error: %s", desc)
            on_error(desc)
            return
        if result is not None and result.isFinal():
            called["done"] = True
            text = result.bestTranscription().formattedString()
            logger.info("Transcription: %s", (text or "")[:100])
            on_done(text if text else "")

    recognizer.recognitionTaskWithRequest_resultHandler_(request, handler)
