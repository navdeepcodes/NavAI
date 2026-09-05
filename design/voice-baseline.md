# The voice pipeline as it stands

Measured before anything about it changes, so a later change can be compared
against numbers rather than against an impression. Every figure comes from the
real components — the real microphone, the real `SFSpeechRecognizer`, the real
`say` binary — driven the way `UIController` drives them.

Harness: `tests/measure_voice_baseline.py`.
Raw data: `design/evidence/voice_baseline.json`.
Machine: 16 GB Apple Silicon Mac, `qwen3.5:9b` at 40,960 context, entirely on GPU.

---

## The pipeline

```
wake word ──┐
            ▼
      PushToTalkRecorder          sounddevice InputStream, 16 kHz mono,
      (voice/recorder.py)         100 ms blocks
            │                     calibrates a noise floor for 0.3 s, then
            │                     ends on 1.2 s of silence (max 30 s)
            ▼
        WAV on disk               audio/recordings/voice_input.wav
            │
            ▼
   transcribe_blocking            SFSpeechRecognizer, on-device
   (voice/transcriber.py)
            │  text
            ▼
       CoreRuntime                the same loop typed input uses — voice is
    (brain/core_runtime.py)       an input method, not a separate path
            │  streamed tokens
            ▼
  UIController._on_token          buffers, splits on sentence punctuation,
 (ui/controller/ui_controller)    hands each completed sentence to the Speaker
            │
            ▼
         Speaker                  `say -v Samantha -r 185`, one subprocess
     (voice/speaker.py)           per utterance, queued
            │
            ▼
        loudspeaker
```

Barge-in runs backwards through the same structure: the wake-word detector
stays live while Mike is speaking, and firing it calls `Speaker.stop()`,
which clears the queue and terminates the running `say` process.

---

## Measurements

Five repeats each; min / median / max, because a mean hides a stutter.

| Stage | min | median | max |
|---|---:|---:|---:|
| Microphone startup (`start()` returns) | 77 ms | **90 ms** | 96 ms |
| Speech recognition of 1.64 s of audio | 103 ms | **104 ms** | 573 ms |
| `speak()` returns | 1.5 ms | **2.1 ms** | 9.0 ms |
| `say` process actually running | 1.5 ms | **2.1 ms** | 9.0 ms |
| Barge-in (`stop()` to silence) | 1.6 ms | **4.6 ms** | 4.6 ms |

Recognition runs at a **0.12–0.16 realtime factor** — 1.64 s of speech
transcribed in about 0.10 s — and it got the sentence exactly right on every
repeat. The 573 ms outlier is the first call in a process, which pays for
recogniser setup; every subsequent call sits at ~104 ms.

### End to end

One real question, through the whole pipeline, with the real brain:

| Segment | |
|---|---:|
| Recognition | 105 ms |
| → first token from the brain | 622 ms |
| → first complete sentence | 982 ms |
| → audio playing | 7 ms |
| **End of speech to first audio** | **~1.1 s** |

Repeated with a cold model the same measurement gave 1.7 s, the difference
being entirely the brain's first token.

**The brain is ~90% of the latency.** Recognition is 105 ms and starting audio
is 7 ms; waiting for the model to produce a full sentence is 982 ms. Any work
aimed at making Mike feel faster to talk to has to start there — a faster TTS
engine could at most save the 7 ms.

---

## Blocking

Measured rather than argued: a real tool call (`calculate`) timed twenty times
in silence and twenty times while audio was playing, with the audio confirmed
still playing throughout.

| | median | max |
|---|---:|---:|
| Tool call while silent | 0.0 ms | 0.3 ms |
| Tool call while speaking | 0.0 ms | 0.1 ms |

**TTS does not block the main runtime, and does not block the agent/tool
loop.** It cannot: `say` is a separate process and `Speaker.speak()` only
spawns it. Playback is interruptible immediately — 4.6 ms from the decision to
silence — because stopping is a `terminate()` on that process, not a flag the
audio layer has to notice.

---

## Cost

| | |
|---|---|
| Mike's own RSS, baseline | 128 MB |
| with the microphone stream open | 128 MB |
| with microphone and speech together | 128 MB |
| `say` subprocess | 17% of one core, 41 MB |
| GPU | none — the GPU is entirely the language model's |

Recognition and synthesis are macOS system services in their own processes, so
they cost Mike nothing resident. This is the thing to weigh against any local
neural TTS: the current pipeline's marginal memory cost is effectively zero,
and its marginal GPU cost is zero, on a machine where the brain already holds
6.9 GB of 16 GB.

---

## Stability

Covered by `tests/test_voice_lifecycle_stress.py` and re-run for this audit:
ten recorder start/stop cycles, ten wake-word cycles, twenty speak/stop cycles
with no orphaned `say` processes, five full window startup/teardown cycles with
thread counting either side, and twenty hide/show cycles. Background operation
is stable across all of them.

Failure isolation holds in both directions: a dead microphone, a missing `say`
binary, a wake-word callback that raises, and a background service that fails
to start all leave the core runtime answering.

---

## What this baseline says about changing anything

1. **Latency is not a TTS problem.** 7 ms of the ~1.1 s belongs to speech
   synthesis. Replacing it cannot make Mike meaningfully faster to talk to.
2. **The current engine is free.** Zero resident memory, zero GPU, 17% of one
   core while actually speaking.
3. **Barge-in is nearly instant.** 4.6 ms is `terminate()` on a subprocess.
   *(This section originally predicted that a neural engine would be
   substantially worse here. It was measured afterwards and the prediction was
   wrong — abandoning a streaming MLX generator costs 0.1–0.6 ms, and the
   committed-audio tail is bounded by the streaming interval. See
   `design/tts-candidate-qwen3.md`.)*
4. **Voice quality is the one real weakness.** `say -v Samantha` is a 2005-era
   formant-ish concatenative voice, and it is what makes Mike sound like a
   utility. That is a quality argument, not a latency or resource argument, and
   it should be made on its own terms.

Nothing here has been changed. This is the measurement, not a proposal.
