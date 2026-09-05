# Mike's voice

Mike speaks with one of two voices, and can always fall back to the second.

| | |
|---|---|
| **Ryan** (`qwen`) | Qwen3-TTS 0.6B, 4-bit, running locally. Natural, conversational. Needs installing. |
| **Samantha** (`native`) | The macOS system voice. Always present, costs nothing, sounds like a utility. |

Mike works without the neural voice. If it is missing, broken, or fails
mid-sentence, he finishes speaking in the system voice and records why in the
log. He never goes silent because the better voice is unavailable.

## Installing the neural voice

```bash
./scripts/install_voice.sh
```

Roughly 2.4 GB on disk and a few minutes, most of it downloading the model.
Apple Silicon only — it runs through MLX.

Then set `voice_provider` to `qwen` in
`~/Library/Application Support/Mike/preferences.json`.

## Why it lives in its own environment

The speech runtime pins `transformers==5.0.0rc3`, a release candidate. Mike's
own environment is certified against a passing test suite and should not take
on a pre-release dependency, so the voice gets its own — installed, upgraded
and removed without touching the assistant.

It also runs as a separate process, which is what makes interruption
instant: stopping Mike mid-sentence is killing a process, not asking a
library to please stop.

## Settings

All in `~/Library/Application Support/Mike/preferences.json`.

| Setting | Default | |
|---|---|---|
| `voice_provider` | `native` | `native` or `qwen` |
| `voice_qwen_speaker` | `Ryan` | Ryan, Aiden, Serena, Vivian, Uncle_Fu, Dylan, Eric, Ono_Anna, Sohee |
| `voice_qwen_instruct` | see below | How Mike should sound, in plain English |

The default delivery instruction is:

> Picking up a conversation. Calm, grounded, matter-of-fact.

Two things learned by listening to a lot of candidates:

**Describe the situation, not the prohibitions.** "Do not sound theatrical"
produced a slow, over-articulated reading of every word. "Picking up a
conversation" produced natural delivery — and, without speed being mentioned
at all, cut the reading from eleven seconds to seven.

**Keep it short.** Instructions past roughly sixty characters destabilised
generation and truncated sentences mid-word.

## What it costs

Measured on an M4 with 16 GB, with the 6.2 GB language model also resident:

| | Ryan | Samantha |
|---|---|---|
| Resident memory | ~0.9 GB | none |
| Time to first audio | ~240 ms | ~2 ms |
| Four-sentence reply | 24.9 s | 11.8 s |
| Interruption | ~1.4 ms | ~4.6 ms |

The brain dominates conversational latency either way: in a real exchange,
first audio was 3.3 s with Ryan against 3.0 s with Samantha, because most of
that wait is the model thinking. Where Ryan costs you is the length of the
reply itself — he speaks about 40% slower, and generation adds to that.

## If something goes wrong

Failures are handled rather than announced: Mike switches to the system voice
mid-reply and carries on. To see what actually happened:

```python
from voice import diagnostics
diagnostics.summary()      # counts: fallbacks, failures, truncations, latency
diagnostics.recent()       # the last utterances, one line each
```

The spoken text is never recorded — only its length — and nothing leaves the
machine.

### Runaway generation

The model can occasionally produce far more audio than the text warrants:
once in twenty-eight generations, measured, it produced 96 seconds of speech
for a seven-second sentence. A duration ceiling stops that before any of it
is audible, and marks the voice unwell so the rest of the reply comes from
the system voice.

The ceiling is proportional to the text with generous headroom, and is
configurable:

| Variable | Default | |
|---|---|---|
| `MIKE_QWEN_TTS_MAX_SECONDS` | 60 | absolute cap on one utterance |
| `MIKE_QWEN_TTS_CEILING_FACTOR` | 1.8 | multiple of the slowest observed reading |
| `MIKE_QWEN_TTS_MIN_SECONDS` | 4 | floor, so short replies are never clipped |
| `MIKE_VOICE_HOME` | see above | where the voice is installed |
