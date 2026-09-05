"""The real question: end of user speech to first audible Mike, both voices.

Not TTS time-to-first-audio. The whole pipeline — recognition, the real
brain, sentence splitting, then speech — because that is what a person
actually waits through, and the earlier baseline showed the brain is most of
it. A faster or slower TTS moves a small part of a larger number.

    venv/bin/python tests/measure_voice_integrated.py [--turns 10]
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MIKE_DATA_DIR", str(Path.home() / ".mike-brain-lab"))

QUESTIONS = [
    "What is the capital of France",
    "How many days are there in February",
    "What is two hundred and forty seven plus five hundred and twelve",
    "Name three primary colours",
    "What year did the first moon landing happen",
]


def sysmem() -> dict:
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    vals, ps = {}, 16384
    for line in out.splitlines():
        if "page size of" in line:
            ps = int(line.split()[-2]); continue
        if ":" in line:
            k, v = line.split(":", 1)
            try: vals[k.strip()] = int(v.strip().rstrip("."))
            except ValueError: pass
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    used = float(swap.split("used =")[1].split("M")[0]) / 1024 if "used =" in swap else 0
    return {"free_gb": round(vals.get("Pages free", 0) * ps / 1073741824, 2),
            "swap_gb": round(used, 2)}


def say_to_file(text: str, path: Path) -> bool:
    done = subprocess.run(
        ["say", "-o", str(path), "--data-format=LEI16@16000", text], capture_output=True)
    return done.returncode == 0 and path.exists()


def one_turn(runtime, speaker, question: str, wav: Path) -> dict:
    """One complete exchange, timed the way a person experiences it."""
    from voice.transcriber import transcribe_blocking

    start = time.perf_counter()
    heard = transcribe_blocking(str(wav), timeout=20.0)
    recognised = time.perf_counter()

    first_token = first_sentence = audible = None
    buffer = ""
    for kind, payload in runtime.process_streaming(
        heard or question, confirm_callback=lambda d: False
    ):
        if kind != "token":
            continue
        if first_token is None:
            first_token = time.perf_counter()
        buffer += payload
        if first_sentence is None and any(p in buffer for p in ".!?"):
            first_sentence = time.perf_counter()
            speaker.speak_sentence(buffer)
            break

    if first_sentence is None and buffer.strip():
        first_sentence = time.perf_counter()
        speaker.speak_sentence(buffer)

    deadline = time.perf_counter() + 15.0
    while time.perf_counter() < deadline:
        if speaker.is_speaking():
            audible = time.perf_counter()
            break
        time.sleep(0.002)

    ms = lambda a, b: round((b - a) * 1000) if a and b else None
    result = {
        "question": question, "heard": heard, "reply": buffer.strip()[:120],
        "recognition_ms": ms(start, recognised),
        "brain_first_token_ms": ms(recognised, first_token),
        "brain_first_sentence_ms": ms(recognised, first_sentence),
        "tts_first_audio_ms": ms(first_sentence, audible),
        "END_TO_FIRST_AUDIO_ms": ms(start, audible),
        "fell_back": speaker.fell_back,
    }
    # Let it speak a moment so this is a real conversation, then move on.
    time.sleep(0.8)
    speaker.stop()
    return result


def run_voice(name: str, questions: list[str], wavs: dict) -> dict:
    from brain.core_runtime import CoreRuntime
    from voice.providers import get_provider
    from voice.speaker import Speaker

    provider = get_provider(name)
    speaker = Speaker(provider=provider)
    if hasattr(provider, "warm_up"):
        t = time.perf_counter()
        provider.warm_up()
        warm = round(time.perf_counter() - t, 2)
    else:
        warm = 0.0

    runtime = CoreRuntime()
    before = sysmem()
    turns = [one_turn(runtime, speaker, q, wavs[q]) for q in questions]
    after = sysmem()

    speaker.shutdown()
    return {
        "provider": provider.name,
        "actually_used": "native" if speaker.fell_back else provider.name,
        "warm_up_s": warm,
        "mem_before": before, "mem_after": after,
        "rss_peak_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1073741824, 2),
        "turns": turns,
    }


def summarise(label: str, run: dict) -> None:
    values = [t["END_TO_FIRST_AUDIO_ms"] for t in run["turns"] if t["END_TO_FIRST_AUDIO_ms"]]
    tts = [t["tts_first_audio_ms"] for t in run["turns"] if t["tts_first_audio_ms"] is not None]
    if not values:
        print(f"{label}: no successful turns")
        return
    ordered = sorted(values)
    print(f"\n{label} ({run['actually_used']}) — {len(values)} turns")
    print(f"  end of speech -> first audio : min {ordered[0]} / "
          f"median {ordered[len(ordered)//2]} / max {ordered[-1]} ms")
    if tts:
        t = sorted(tts)
        print(f"  of which TTS                : median {t[len(t)//2]} ms")
    print(f"  memory  free {run['mem_before']['free_gb']} -> {run['mem_after']['free_gb']} GB, "
          f"swap {run['mem_before']['swap_gb']} -> {run['mem_after']['swap_gb']} GB")
    print(f"  fell back to native          : {any(t['fell_back'] for t in run['turns'])}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=5)
    parser.add_argument("--voices", default="native,qwen")
    args = parser.parse_args()

    questions = (QUESTIONS * ((args.turns // len(QUESTIONS)) + 1))[:args.turns]

    tmp = Path(tempfile.mkdtemp(prefix="mike-voice-e2e-"))
    wavs = {}
    for q in set(questions):
        path = tmp / (str(abs(hash(q))) + ".wav")
        assert say_to_file(q, path), q
        wavs[q] = path

    report = {}
    for voice in args.voices.split(","):
        voice = voice.strip()
        print(f"\n=== {voice} ===", flush=True)
        report[voice] = run_voice(voice, questions, wavs)
        summarise(voice, report[voice])

    out = Path(__file__).parent.parent / "design" / "evidence" / "voice_integrated.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nevidence: {out}")


if __name__ == "__main__":
    main()
