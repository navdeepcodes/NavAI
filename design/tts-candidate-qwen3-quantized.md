# Qwen3-TTS 0.6B quantized, measured against Samantha

Follow-on to `design/tts-candidate-qwen3.md`, which found the fp32 build
impractical on this machine. This is the quantized configuration, which is a
substantially different proposition. Mike's voice path is still untouched.

**Machine:** Apple M4, 16 GB. **Control:** `design/voice-baseline.md`.

---

## What quantization actually buys

The 0.6B model is two parts, and only one of them quantizes:

| | LM weights | speech codec | total on disk |
|---|---:|---:|---:|
| fp32 | 1.72 GB | 0.68 GB | 2.40 GB |
| 8-bit | 1.30 GB | 0.68 GB | 1.99 GB |
| 4-bit | 1.02 GB | 0.68 GB | 1.71 GB |

The 0.68 GB codec is a floor no quantization removes. So "roughly 1 GB" is
not reachable on disk — but it *is* reachable in resident memory, which is
what matters.

---

## Resident memory — with a correction

| | resident (model loaded once) |
|---|---:|
| fp32 | 2.52 GB |
| **4-bit** | **0.88 GB** |

**An earlier figure in this investigation was wrong and is corrected here.**
The first quantized benchmark reported 2.6 GB peak RSS for 4-bit, which would
have made quantization look pointless. That number was an artifact of the
harness: it called `generate_audio(model=<path>)`, which loads a *second*
copy of the model alongside the one already held. Measured with a single
loaded model — the way any real integration would work — 4-bit resides in
**0.88 GB**.

That is the target hit almost exactly, and it is a 2.9× reduction on fp32.

---

## Latency

| | Samantha | fp32 | **4-bit** |
|---|---:|---:|---:|
| Model load | — | 1.44 s | **1.21 s** |
| TTFA, non-streaming (short) | 0.002 s | — | **1.07 s** |
| TTFA, non-streaming (long) | 0.002 s | 4.93 s | **2.57 s** |
| **TTFA, streaming @0.5 s (short)** | **0.002 s** | — | **0.18 s** |
| **TTFA, streaming @0.5 s (long)** | **0.002 s** | 0.36–0.47 s | **0.26 s** |
| RTF (short) | 0.44 | 0.91 | **0.60–0.65** |
| RTF (long) | 0.09 | 0.82 | **0.43–0.67** |
| Barge-in, abandon generator | 4.6 ms (kill process) | 0.1–0.6 ms | **0.09 ms** |

Quantization roughly halves both time-to-first-audio and synthesis time
against fp32. Against the measured baseline, end-of-speech to first audio
would go from **~1.1 s to ~1.3 s** — a 0.2 s regression, where fp32 cost 0.4 s.

---

## Sustained conversation

Eight consecutive replies of the kind Mike actually gives, streaming:

| turn | TTFA | total | RSS |
|---:|---:|---:|---:|
| 0 | 0.194 s | 1.37 s | flat |
| 1 | 0.190 s | 1.82 s | flat |
| 2 | 0.192 s | 1.88 s | flat |
| 3 | 0.185 s | 2.79 s | flat |
| 4 | 0.186 s | 2.40 s | flat |
| 5 | 0.185 s | 1.45 s | flat |
| 6 | 0.185 s | 1.07 s | flat |
| 7 | 0.181 s | 2.36 s | flat |

**No drift and no growth.** TTFA is flat to within 13 ms across eight turns
and resident memory does not move. Whatever else is true, this does not
degrade over a conversation.

---

## Alongside the 9B brain

Measured by loading the brain first, then the TTS, then synthesising five
times — not by adding numbers together.

| | free | inactive | swap used |
|---|---:|---:|---:|
| Brain resident (Ollama 6.16 GB) | 0.07 GB | 2.05 GB | 5.09 GB |
| **+ 4-bit TTS loaded** | 0.07 GB | 1.27 GB | **5.30 GB** (+0.21) |
| after five spoken turns | 0.12 GB | 1.31 GB | **5.67 GB** (+0.58) |

For comparison, fp32 pushed **+1.1 GB** into swap on load alone.

TTFA with the brain resident: 0.41 s on the first turn, then 0.19 s and flat.
The model coexists, costs about 0.2 GB of swap to load and about 0.6 GB across
a short conversation, and does not slow down.

This machine is genuinely tight — swap was already at 5.1 GB of 6 GB before
any of this. 4-bit fits; it does not fit *comfortably*, and that is a property
of the machine rather than of the model.

---

## Two reliability findings

**1. It occasionally runs away.** One generation in 28 of the same sentence
produced **96 seconds of audio for a seven-second line** — Mike rambling for a
minute and a half. Twenty-eight trials: 1 runaway, so roughly 3.6%. Rare, not
negligible, and it has no equivalent in the current engine.

Mitigable in integration — a duration ceiling derived from the text length
would cut it off — but it is a new failure mode in a path that currently
cannot fail.

**2. It is not deterministic.** The same sentence came out anywhere from
**6.2 s to 10.0 s** long across 25 clean runs. Samantha says it in 5.4 s,
every time. So Qwen is both slower-paced and variable, which matters for a
voice that reads back figures.

---

## 8-bit: not benchmarked, and why

8-bit was downloaded but not measured. It sits between fp32 and 4-bit on
every axis that was already measured — its LM weights are 1.30 GB against
4-bit's 1.02 GB, so it costs more memory for at most a small quality gain,
and 4-bit already met the memory target while beating fp32 on latency.

The deciding criterion is voice quality, and that is judged by listening to
samples rather than by a fourth column of numbers. If 4-bit sounds close but
not quite good enough, 8-bit is the obvious next thing to try; if 4-bit does
not sound clearly better than Samantha, 8-bit will not rescue it.

## Where this leaves it

Quantization changes the practical verdict entirely:

| | fp32 | 4-bit | verdict |
|---|---|---|---|
| Resident | 2.52 GB | **0.88 GB** | target met |
| Swap cost beside the brain | +1.1 GB | **+0.2 GB** | acceptable |
| Streaming TTFA | 0.36–0.47 s | **0.18–0.26 s** | +0.2 s vs today |
| Sustained | untested | **flat over 8 turns** | no degradation |
| Barge-in | 0.1–0.6 ms | **0.09 ms** | no regression |
| Runaway generations | untested | **1 in 28** | new failure mode |
| Deterministic length | no | **no** (6.2–10.0 s) | regression |

**The resource argument against this model is now largely answered.** What is
left is exactly what it should be: does it sound clearly better, and is that
worth a 0.2 s delay, ~0.9 GB, a 3.6% runaway rate, and non-deterministic
delivery?

That is a listening decision, not a measurement, and it belongs to the person
who has to hear it every day.
