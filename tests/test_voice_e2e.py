"""Real E2E voice tests — requires microphone and macOS Speech."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — must run before any brain/config import


def test_recorder():
    """Test push-to-talk recorder: start, wait, stop."""
    from voice.recorder import PushToTalkRecorder

    rec = PushToTalkRecorder()
    print("Starting recorder... speak for 3 seconds.")

    ok = rec.start()
    assert ok, "Failed to start recording"
    assert rec.is_recording

    time.sleep(3)

    path = rec.stop()
    assert not rec.is_recording

    if path is None:
        print("WARNING: No audio captured (too quiet or mic issue)")
        return None

    print(f"  Recording saved to: {path}")
    size = os.path.getsize(path)
    print(f"  File size: {size:,} bytes")
    assert size > 1000, "Recording file too small"
    return path


def test_transcribe(audio_path: str):
    """Test macOS native transcription."""
    from voice.transcriber import transcribe_blocking

    print(f"Transcribing {audio_path}...")
    t0 = time.time()
    text = transcribe_blocking(audio_path)
    elapsed = time.time() - t0

    print(f"  Transcription: '{text}'")
    print(f"  Time: {elapsed:.1f}s")
    return text, elapsed


def test_full_pipeline():
    """Record → transcribe → CoreRuntime."""
    from voice.recorder import PushToTalkRecorder
    from voice.transcriber import transcribe_blocking
    from brain.core_runtime import CoreRuntime

    rec = PushToTalkRecorder()

    print("\n" + "=" * 60)
    print("FULL VOICE PIPELINE TEST")
    print("Say: 'What is the capital of France?'")
    print("=" * 60)

    print("\nRecording for 4 seconds... speak now!")
    rec.start()
    time.sleep(4)
    audio_path = rec.stop()

    if not audio_path:
        print("SKIP: No audio captured")
        return

    print("\nTranscribing...")
    t0 = time.time()
    text = transcribe_blocking(audio_path)
    transcribe_time = time.time() - t0
    print(f"  Transcription: '{text}' ({transcribe_time:.1f}s)")

    if not text:
        print("SKIP: Empty transcription")
        return

    print("\nSending to CoreRuntime...")
    runtime = CoreRuntime()
    t0 = time.time()
    full_text = ""
    tools = []
    for event_type, payload in runtime.process_streaming(text):
        if event_type == "token":
            full_text += payload
        elif event_type == "tool_start":
            tools.append(payload)

    runtime_time = time.time() - t0

    print(f"  Mike response: {full_text[:300]}")
    print(f"  Tools used: {tools}")
    print(f"  Runtime time: {runtime_time:.1f}s")
    print(f"  Total voice-to-response: {transcribe_time + runtime_time:.1f}s")


if __name__ == "__main__":
    print("=" * 60)
    print("VOICE INPUT — REAL E2E TESTS")
    print("=" * 60)

    # Test 1: Recording
    print("\n========== TEST 1: Recorder ==========")
    audio_path = test_recorder()

    # Test 2: Transcription
    if audio_path:
        print("\n========== TEST 2: Transcription ==========")
        text, elapsed = test_transcribe(audio_path)
        if text:
            print(f"  PASS: Got transcription in {elapsed:.1f}s")
        else:
            print("  WARN: Empty transcription")
    else:
        print("\n========== TEST 2: SKIPPED (no audio) ==========")

    # Test 3: Full pipeline
    print("\n========== TEST 3: Full Pipeline ==========")
    test_full_pipeline()

    print("\n" + "=" * 60)
    print("VOICE E2E TESTS COMPLETE")
    print("=" * 60)
