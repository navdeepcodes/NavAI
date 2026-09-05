# Qwen3-TTS 0.6B, measured against `say`/Samantha

An investigation, not a change. Nothing in Mike's voice path was touched. The
control is `design/voice-baseline.md`, measured on the same machine.

**Machine:** Apple M4, 16 GB unified memory. Worth stating up front: the
published Apple-Silicon figures for this model were measured on an **M5**, so
this machine is the slower case, not the faster one.

---

## The candidate

| | |
|---|---|
| Model | `Qwen/Qwen3-TTS-12Hz-0.6B-Base`, via the MLX conversion `cr2k2/Qwen3-TTS-12Hz-0.6B-Base-fp32` |
| Parameters | 0.6 B (the base repo reports 0.9 B including the codec stack) |
| On disk | **2.4 GB** (fp32 MLX safetensors) |
| Model licence | **Apache 2.0** — commercial use permitted |
| Runtime licence | `mlx-audio` MIT; a separate pure-C engine also exists under MIT |
| Runtime | `mlx-audio>=0.3.2` + `transformers==5.0.0rc3`, ~700 MB of dependencies |
| GPU | Metal, via MLX. Shares the same unified memory as the brain |
| Languages | 10, including English |
| Voices | Named presets (Ethan, Chelsie, Cherry, Serena…) plus 3-second voice cloning |

The dependency pin is worth flagging: `transformers==5.0.0rc3` is a release
candidate. It was installed into a throwaway virtualenv outside the project,
never into Mike's certified environment.

---

## Latency

All figures warm unless stated. `say` is the control.

| | Qwen3-TTS 0.6B | `say`/Samantha |
|---|---:|---:|
| Model load (cold) | 1.44 s | — |
| First synthesis incl. load | 3.46 s | — |
| **Time to first audio, non-streaming** | **4.93 s** | **0.002 s** |
| Time to first audio, streaming @ 2.0 s chunks | 1.43–1.94 s | — |
| **Time to first audio, streaming @ 0.5 s chunks** | **0.36–0.47 s** | **0.002 s** |
| Full synthesis, short sentence (2.5 s audio) | 2.16–2.35 s | 0.70 s |
| Full synthesis, long sentence (6.6 s audio) | 5.21–5.67 s | 0.44 s |
| Real-time factor, short | 0.91 | 0.44 |
| Real-time factor, long | 0.82 | 0.09 |

Non-streaming is disqualifying on its own — five seconds of silence before a
reply begins. **Streaming at 0.5 s chunks is the only configuration worth
discussing**, and it changes the picture substantially: 0.36–0.47 s to first
audio rather than 4.93 s.

Against the measured baseline, end-of-speech to first audio would go from
**~1.1 s to ~1.5 s**. That is a real regression of roughly a third, and it is
much smaller than the raw synthesis numbers suggest. It is not a latency
improvement, and no honest reading of these numbers makes it one.

---

## Memory — the actual constraint

Measured by loading the brain first and then synthesising, rather than by
adding two numbers together.

| | free | inactive | compressed | swap used |
|---|---:|---:|---:|---:|
| Idle | 5.70 GB | 3.03 GB | 0.96 GB | 4.54 GB |
| Brain resident (Ollama 6.18 GB) | 0.06 GB | 2.24 GB | 1.90 GB | 4.53 GB |
| **Brain + TTS both resident** | 1.84 GB | **0.44 GB** | 2.29 GB | **5.65 GB** |

The TTS model peaks at **2.5–3.6 GB** on its own. Loading it while the brain
is resident consumed nearly all remaining inactive memory and pushed **an
extra 1.1 GB into swap**, on a machine whose swap was already at 4.5 GB of
6 GB. Synthesis still completed — 4.73 s with the brain resident — so this is
pressure rather than failure. But it is pressure on a machine that has none
to spare.

**They can coexist. They should not, in this configuration.** The fp32 build
is the wrong one to ship: an INT8 or INT4 quantisation would be roughly
0.8–1.3 GB instead of 2.5 GB, and the pure-C engine reports 0.69 and 0.52 RTF
for those on Apple Silicon. If this model is adopted, it should be adopted
quantised, and that should be benchmarked separately.

---

## Barge-in — and a correction

The voice baseline predicted that barge-in would get worse with a neural
engine. **That prediction was wrong**, and the measurement says so:

| | |
|---|---:|
| Abandoning the generator mid-stream | **0.1–0.6 ms** |
| Audio already committed to the player | up to one chunk (0.5 s at the streaming interval above) |
| Current `say` barge-in | 4.6 ms |

Abandoning an MLX generator is just not consuming it, which costs nothing.
The committed-chunk tail is real but bounded by the streaming interval, and
stopping the player is the same operation Mike already performs. Barge-in is
roughly a wash, not a regression.

---

## Voice quality

Not measurable here, and the deciding criterion. Matched samples of one
sentence were produced from Samantha and from three Qwen voices and handed to
the person who has to listen to it.

The one thing worth recording: the model card for the 0.6B states it produces
"noticeably lower quality voice cloning than the 1.7B". That is about cloning
rather than the preset voices, but it is a signal that **the smallest viable
candidate is also the weakest one** — and voice quality is the entire reason
to consider this change.

---

## Where this leaves it

The case for Qwen3-TTS rests on voice quality alone, and it has to be a clear
win to be worth what it costs:

- **+2.5 GB resident** (or ~1 GB quantised) on a 16 GB machine already
  swapping, alongside a 6.2 GB brain
- **+0.4 s** to first audio, and only if streaming at 0.5 s chunks
- **+2.4 GB disk**, on a volume at 94% full
- a release-candidate dependency pin in the runtime
- a new failure surface in a path that currently cannot fail, because today's
  engine is an OS binary

Against that: Samantha costs nothing, starts in 2 ms, and sounds like 2005.

If the samples are a clear improvement, the next step is not integration — it
is benchmarking a **quantised** build, because the fp32 memory cost is the
blocker and quantisation is the thing that removes it. If the samples are
merely different, keep Samantha.
