"""Measure the voice pipeline as it stands, before anything about it changes.

Every number here comes from the real components — the real microphone, the
real `SFSpeechRecognizer`, the real `say` binary — driven the way
UIController drives them. Nothing is simulated and nothing is estimated.

The point is a baseline, not a verdict. A later change to any stage can be
compared against these figures instead of against an impression.

    venv/bin/python tests/measure_voice_baseline.py [--repeats 5]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MIKE_DATA_DIR", str(Path.home() / ".mike-brain-lab"))

SPOKEN = "What is the capital of France"


def stat(name: str, samples: list[float], unit: str = "ms") -> dict:
    """Report the spread, not just an average. A mean hides the stutter."""
    if not samples:
        return {"measurement": name, "n": 0}
    ordered = sorted(samples)
    return {
        "measurement": name,
        "n": len(samples),
        "min": round(ordered[0], 1),
        "median": round(ordered[len(ordered) // 2], 1),
        "max": round(ordered[-1], 1),
        "unit": unit,
    }


def say_to_file(text: str, path: Path) -> bool:
    """Synthesise speech to a file, to feed recognition without a human."""
    done = subprocess.run(
        ["say", "-o", str(path), "--data-format=LEI16@16000", text],
        capture_output=True,
    )
    return done.returncode == 0 and path.exists()


# ── stages ────────────────────────────────────────────────

def measure_microphone_startup(repeats: int) -> dict:
    from voice.recorder import PushToTalkRecorder

    samples = []
    for _ in range(repeats):
        recorder = PushToTalkRecorder()
        started = time.perf_counter()
        ok = recorder.start()
        samples.append((time.perf_counter() - started) * 1000)
        recorder.stop()
        if not ok:
            return {"measurement": "microphone startup", "error": "recorder refused to start"}
        time.sleep(0.1)
    return stat("microphone startup (start() returns)", samples)


def measure_recognition(repeats: int) -> tuple[dict, dict]:
    from voice.transcriber import transcribe_blocking

    wav = Path(tempfile.mkdtemp()) / "spoken.wav"
    if not say_to_file(SPOKEN, wav):
        return ({"measurement": "speech recognition", "error": "could not synthesise audio"},
                {})

    audio_seconds = subprocess.run(
        ["afinfo", "-r", str(wav)], capture_output=True, text=True,
    ).stdout
    duration = 0.0
    for line in audio_seconds.splitlines():
        if "estimated duration" in line:
            duration = float(line.split()[-2])

    samples, texts = [], []
    for _ in range(repeats):
        started = time.perf_counter()
        text = transcribe_blocking(str(wav), timeout=20.0)
        samples.append((time.perf_counter() - started) * 1000)
        texts.append(text)

    result = stat(f"speech recognition of {duration:.1f}s of audio", samples)
    result["recognised"] = texts[0]
    result["audio_seconds"] = round(duration, 2)
    if samples and duration:
        result["realtime_factor"] = round((sum(samples) / len(samples) / 1000) / duration, 2)
    return result, {"wav": str(wav), "duration": duration}


def measure_playback_start(repeats: int) -> dict:
    """From asking Mike to speak to audio actually being produced.

    `say` is a subprocess: speak() returns as soon as it is spawned, which is
    not the same as sound leaving the speaker. Both are measured — the call
    cost, and the time until the process is genuinely running.
    """
    from voice.speaker import Speaker

    call, audible = [], []
    for _ in range(repeats):
        speaker = Speaker()
        started = time.perf_counter()
        speaker.speak("The capital of France is Paris.")
        call.append((time.perf_counter() - started) * 1000)

        while speaker._process is None or speaker._process.poll() is not None:
            if time.perf_counter() - started > 3:
                break
            time.sleep(0.002)
        audible.append((time.perf_counter() - started) * 1000)

        speaker.stop()
        time.sleep(0.1)
    return {
        "speak() returns": stat("speak() returns", call),
        "say process running": stat("say process running", audible),
    }


def measure_barge_in(repeats: int) -> dict:
    from voice.speaker import Speaker

    samples = []
    for _ in range(repeats):
        speaker = Speaker()
        speaker.speak(
            "This is a long sentence that will be interrupted well before it "
            "finishes, which is what barge-in has to be able to do."
        )
        time.sleep(0.4)
        if not speaker.is_speaking():
            continue
        started = time.perf_counter()
        speaker.stop()
        samples.append((time.perf_counter() - started) * 1000)
        assert not speaker.is_speaking()
        time.sleep(0.1)
    return stat("barge-in (stop() to silence)", samples)


def measure_blocking() -> dict:
    """Does speaking block the runtime, or the agent loop?

    Measured rather than reasoned about: run a real tool call while audio is
    playing, and compare it against the same call in silence.
    """
    from brain.core_runtime import CoreRuntime
    from voice.speaker import Speaker

    runtime = CoreRuntime()

    def time_a_tool() -> float:
        started = time.perf_counter()
        runtime._execute_tool("calculate", {"expression": "2417 + 3168 + 912"})
        return (time.perf_counter() - started) * 1000

    quiet = [time_a_tool() for _ in range(20)]

    speaker = Speaker()
    speaker.speak(
        "Mike is speaking a fairly long sentence now, and while that audio "
        "plays the tool loop should keep running at exactly the same speed."
    )
    time.sleep(0.3)
    speaking = [time_a_tool() for _ in range(20)]
    still_playing = speaker.is_speaking()
    speaker.stop()

    return {
        "tool call while silent": stat("tool call while silent", quiet),
        "tool call while speaking": stat("tool call while speaking", speaking),
        "audio still playing during the measurement": still_playing,
        "verdict": (
            "TTS does not block the tool loop"
            if still_playing and max(speaking) < max(quiet) * 3 + 5
            else "inconclusive — audio ended too early to tell"
            if not still_playing else "TTS appears to interfere with the tool loop"
        ),
    }


def measure_resources() -> dict:
    """What the voice stack costs while it is running."""
    import resource

    from voice.recorder import PushToTalkRecorder
    from voice.speaker import Speaker

    def rss_mb() -> float:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)

    baseline = rss_mb()

    recorder = PushToTalkRecorder()
    recorder.start()
    time.sleep(0.5)
    with_mic = rss_mb()

    speaker = Speaker()
    speaker.speak("Measuring what this costs to run.")
    time.sleep(0.4)
    with_both = rss_mb()

    say_cpu = subprocess.run(
        ["ps", "-o", "%cpu=,rss=", "-p", str(speaker._process.pid)],
        capture_output=True, text=True,
    ).stdout.split() if speaker._process else []

    speaker.stop()
    recorder.stop()

    return {
        "process RSS baseline MB": round(baseline, 1),
        "process RSS with microphone open MB": round(with_mic, 1),
        "process RSS with microphone and speech MB": round(with_both, 1),
        "say subprocess %cpu / RSS KB": say_cpu or "not sampled",
        "note": (
            "Speech synthesis and recognition are macOS system services in "
            "separate processes, so their cost does not appear in Mike's own "
            "RSS. No GPU is used by the voice path; the GPU is entirely the "
            "language model's."
        ),
    }


def measure_end_to_end() -> dict:
    """End of user speech to first audio, through the whole real pipeline."""
    from brain.core_runtime import CoreRuntime
    from voice.speaker import Speaker
    from voice.transcriber import transcribe_blocking

    wav = Path(tempfile.mkdtemp()) / "question.wav"
    if not say_to_file(SPOKEN, wav):
        return {"error": "could not synthesise the question"}

    runtime = CoreRuntime()
    speaker = Speaker()

    started = time.perf_counter()
    heard = transcribe_blocking(str(wav), timeout=20.0)
    recognised_at = time.perf_counter()

    first_token_at = None
    first_sentence_at = None
    audio_at = None
    buffer = ""
    # UIController speaks each completed sentence as it arrives, so the number
    # that matters is when the *first* one is ready — not when the whole reply
    # finishes. If the reply never contains sentence punctuation (a very short
    # answer, or a turn that ends on a tool result), the whole reply is spoken
    # at the end, which is the same thing the controller does.
    for kind, payload in runtime.process_streaming(
        heard or SPOKEN, confirm_callback=lambda d: False
    ):
        if kind != "token":
            continue
        if first_token_at is None:
            first_token_at = time.perf_counter()
        buffer += payload
        if first_sentence_at is None and any(p in buffer for p in ".!?"):
            first_sentence_at = time.perf_counter()
            speaker.speak_sentence(buffer)
            break

    if first_sentence_at is None and buffer.strip():
        first_sentence_at = time.perf_counter()
        speaker.speak_sentence(buffer)

    deadline = time.perf_counter() + 2.0
    while time.perf_counter() < deadline:
        if speaker.is_speaking():
            audio_at = time.perf_counter()
            break
        time.sleep(0.002)
    speaker.stop()

    def ms(a, b):
        return round((b - a) * 1000, 1) if a and b else None

    return {
        "recognised": heard,
        "reply so far": buffer.strip()[:160],
        "recognition ms": ms(started, recognised_at),
        "brain first token ms": ms(recognised_at, first_token_at),
        "brain first full sentence ms": ms(recognised_at, first_sentence_at),
        "speech start ms": ms(first_sentence_at, audio_at),
        "end of speech to first audio ms": ms(started, audio_at),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    report: dict = {"repeats": args.repeats}

    print("measuring microphone startup...", flush=True)
    report["microphone"] = measure_microphone_startup(args.repeats)

    print("measuring speech recognition...", flush=True)
    report["recognition"], _ = measure_recognition(args.repeats)

    print("measuring playback start...", flush=True)
    report["playback"] = measure_playback_start(args.repeats)

    print("measuring barge-in...", flush=True)
    report["barge_in"] = measure_barge_in(args.repeats)

    print("measuring whether speech blocks the tool loop...", flush=True)
    report["blocking"] = measure_blocking()

    print("measuring resource cost...", flush=True)
    report["resources"] = measure_resources()

    print("measuring end to end (this runs the real brain)...", flush=True)
    report["end_to_end"] = measure_end_to_end()

    print("\n" + json.dumps(report, indent=2, default=str))

    out = Path(__file__).parent.parent / "design" / "evidence" / "voice_baseline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nevidence: {out}")


if __name__ == "__main__":
    main()
