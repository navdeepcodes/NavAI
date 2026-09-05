# Model-agnostic Mike — architecture

Mike is the constant. The brain is replaceable.

## Before

`brain/core_runtime.py` held an `ollama.Client`, called `client.chat(...)`
directly, read `chunk.message.tool_calls`, and reached into
`tc.function.arguments` — sometimes a dict, sometimes a JSON string, handled
by an inline `isinstance` check. `mike_core.py` built its own second Ollama
client for summarisation. `vision/analyzer.py` built a third. `diagnostics.py`
checked a model constant the runtime didn't actually use. Model failures
arrived as raw exceptions and were matched by substring (`"not found" in
msg.lower()`) in the runtime, so provider-specific wording like "run ollama
pull" was hardcoded three layers above the provider.

Nothing was catastrophically wrong with this — it worked — but it made two
things impossible: swapping the backend without editing the runtime, and
knowing what the current model could actually do.

## After

```
        Mike  (identity, memory, projects, tools, safety, agency, UI)
                              │
                   canonical types only
        ToolCall · StreamEvent · ChatResult · BrainError · Capabilities
                              │
                    brain/providers/ (the boundary)
                              │
              ┌───────────────┴───────────────┐
        OllamaProvider                  (future: Anthropic,
     ollama client, num_ctx,             OpenAI, OpenAI-compatible,
     tool translation, error              anything else)
     wording, capability probe
```

Three new modules, one rewritten:

- `brain/providers/base.py` — canonical types, the `BrainProvider` contract,
  `Capabilities` (declared vs observed), argument normalisation, token
  estimation.
- `brain/providers/ollama_provider.py` — every Ollama-specific fact.
- `brain/providers/__init__.py` — `get_provider()`, the one place
  configuration becomes a brain.
- `brain/context_budget.py` — fits a request to the brain before sending it.
- `brain/diagnostics.py` — rewritten to report the brain actually in use.

`core_runtime.py` no longer imports `ollama` at all.

## The boundary

A provider implements five things: `capabilities()`, `stream()`,
`complete()`, `health()`, and optionally `describe_image()` and
`translate_error()`. Everything else — tools, safety gates, memory, projects,
the agency loop, the UI — is untouched by which brain is in use.

The contract's central rule is that providers **do not raise for model
misbehaviour**. A hallucinated tool name, arguments that aren't an object, an
unreachable server, a parser failure: each becomes a `BrainError` with a
`kind` the runtime can branch on and a sentence a person can read. The
runtime turns that into an assistant message. Nothing reaches the UI as a
traceback, and a malformed call is never executed.

## Capabilities: declared vs observed

`Capabilities` carries `declared_*` (what the provider/model metadata claims)
and `observed_*` (what Mike has actually seen), and `can()` prefers
observation. This distinction is not theoretical — it is the direct lesson of
the Qwen3.5 9B investigation, where the model card said "tools", the model
appeared unable to call tools, and the real cause was Mike truncating its
schemas. A capability is only trustworthy once it has been exercised.

`max_input_tokens` is deliberately separate from `context_tokens`: a model
may advertise 262,144 tokens while the server will only accept a fraction of
whatever `num_ctx` was allocated.

## Context adaptation

`plan_request()` fits the request before it is sent, in a fixed order:

1. drop the oldest conversation turns (the situation summary already carries
   what fell out),
2. only then drop **whole tools**,
3. if it still doesn't fit, fail with a clear `context` error.

**Tool schemas are never truncated.** A model holding half a definition calls
it wrongly, and a wrong tool call is worse than no tool call — which is
precisely what produced `write_file(text=...)` instead of `content`, and
`run_background(directory=...)` instead of `cwd`.

Both constants here are measured, not guessed: Mike's real prompt is 19,800
characters and Ollama reported `prompt_eval_count=4956` for it, giving 4.0
chars/token (the estimator uses 3.8 to err slightly high). The usable
fraction of `num_ctx` is set from two disagreeing observations — Ollama
truncated at 2,050 with `num_ctx=4096`, yet accepted 4,956 tokens with
`num_ctx=8192` — so 0.75 sits above what Mike actually sends while staying
below the full window.

## Tool protocol isolation

Mike's tools are defined once, canonically, and never change per model.
`BrainProvider.normalise_arguments()` is the single place that tolerates
protocol variety: dict, JSON string, or malformed. It returns either a usable
dict or an explicit refusal — never a guess. The runtime consumes
`ToolCall(name, arguments)` and cannot tell which protocol produced it.

`tool_protocol` is recorded on `Capabilities` for diagnostics and humans, but
nothing above the boundary branches on it.

## Vision

Vision is a capability, not an assumption. The runtime asks
`_vision_available()`, and `_vision_brain()` returns the brain itself when it
can see, or a separately configured vision model when it can't. Both
topologies are supported:

- one model for brain and vision (Qwen3.5 9B can do this), and
- a text-only brain paired with a vision model (the current default:
  `qwen3:8b` + `qwen3.5:9b`).

A brain with no vision and no configured vision model produces a plain
explanation, not an error.

## Failure handling

| What happens | What Mike does |
|---|---|
| Model names a tool that doesn't exist | refused before execution, reported |
| Arguments aren't an object | refused, never guessed |
| Backend unreachable | readable message, retry-safe flag set |
| Server can't parse the model's tool syntax | reported as `protocol`, retry-safe |
| Request too large | trimmed, or refused with a clear reason |
| Model has no tool support | tools withheld entirely rather than sent hopefully |
| Model has no vision | says so, rather than attempting the call |

## What is now model-independent

Tools, safety gates, memory, projects, situation summaries, activity, revert,
voice, wake word, the IDE bridge, the agency loop, cancellation, the UI, and
the benchmark harness. Switching the brain is a configuration change.

## What remains model-specific

Only what genuinely must: the contents of
`brain/providers/ollama_provider.py`, and the `NUM_CTX` /
`USABLE_FRACTION_OF_CTX` figures, which are properties of a particular server
rather than of Mike.

## Benchmark: identical Mike, two brains

Same runtime, same tools, same safety gates, same context planning — only the
brain differs. Seven tasks each, objectively verified against real disk and
process state rather than the model's own claim.

| Task | qwen3:8b calls | 8b verified | qwen3.5:9b calls | 9b verified |
|---|---|---|---|---|
| Inspect unfamiliar repo | 1 | no | 0 | no |
| Find and fix a bug | 1 | no | **3** | **yes** |
| Modify multiple files | 1 | no | 4 | no |
| Run tests, respond to failures | 1 | no | 3 | no |
| Diagnose a failed build | 1 | no | 2 | no |
| Recover from broken command | 1 | no | 1 | no |
| Create then modify a file | 2 | no | 0 | no |
| **Verified** | | **0/7** | | **1/7** |
| **Mean tool calls** | **1.1** | | **1.9** | |

The single verified task is the important one. On "find a bug and fix it",
Qwen3.5 9B chained `list_directory` → `read_file` → `edit_file` and the fix
was confirmed by running the tests afterwards. Qwen3:8b made one call and
stopped. That is the multi-step, observation-to-action behaviour that
previous benchmarks found missing in both models — and it only became visible
once tool schemas stopped being truncated.

Both models still overclaim: 8b claimed success on 3 tasks it did not
complete, 9b on 2. The claimed-vs-verified split is what makes that visible.

An honest caveat: this is a small sample on a loaded 8 GB machine, with task
latencies from 18s to 291s. It establishes that 9B sustains longer tool
chains, not a reliable ranking.

## What the earlier verdict got wrong

An earlier conclusion recorded that "Qwen3.5 9B fails tool calling under
Mike's real conditions". That was wrong, and this milestone retracts it. The
model was never the problem — Mike was sending it half a tool schema.
Capability is now measured against Mike's real runtime rather than inferred
from one bad interaction, which is exactly what the declared/observed split
exists to prevent.

---

# Brain Lab — proving the boundary against real, different brains

## Providers added

A second provider, `OpenAICompatibleProvider`, covers every `/chat/completions`
endpoint: DeepSeek, Gemini, OpenRouter, and anything else of that shape. It is
a genuinely different protocol from Ollama — HTTPS rather than a local socket,
SSE rather than a Python iterator, and tool arguments arriving as a **JSON
string** rather than a dict.

Adding it required **no changes above the provider boundary**. Endpoints are
rows in a table in `brain/providers/__init__.py`, not code.

## Credentials, honestly

- **DeepSeek** — no key existed at first; the user supplied one. Working,
  $0.83 balance. Stored in the git-ignored, mode-600 `.env`; never printed.
- **Gemini** — the key already in `.env` was dead (HTTP 401). A replacement
  works, but its free-tier quota was already exhausted, so most of its probe
  is honestly recorded as NOT TESTED rather than failed.
- **OpenRouter** — key valid, free tier.

## Observed capability profiles

Every row below is evidence from Mike actually exercising the capability
through the real provider, not a model card claim.

| Capability | qwen3:8b | qwen3.5:9b | deepseek-v4-flash | gemini-3.6-flash |
|---|---|---|---|---|
| reachable | VERIFIED | VERIFIED | VERIFIED | VERIFIED |
| text | VERIFIED | VERIFIED | VERIFIED | quota |
| streaming | VERIFIED | VERIFIED | VERIFIED | quota |
| tool calling | VERIFIED | VERIFIED | VERIFIED | quota |
| Mike's 30 real tools | VERIFIED | VERIFIED | VERIFIED | quota |
| tool continuation | VERIFIED | VERIFIED | VERIFIED | quota |
| rejects malformed | VERIFIED | VERIFIED | VERIFIED | VERIFIED |
| vision | none declared | **VERIFIED** | none declared | quota |

qwen3.5:9b is the first confirmed **configuration A** brain: one model serving
as both brain and eyes.

## Benchmark — same Mike, different brains

Objectively verified against real disk and process state, never the model's
own claim.

| Task | qwen3:8b | qwen3.5:9b | deepseek-v4-flash |
|---|---|---|---|
| Find and fix a bug | no | **yes** | **yes** |
| Run tests, respond to failures | no | no | **yes** |
| Modify multiple files | no | no | **yes** |
| Diagnose a failed build | no | no | **yes** |
| Recover from broken command | no | no | **yes** |
| Create then modify a file | no | no | **yes** |
| **Verified** | 0/7 | 1/7 | **6/7** |
| Mean tool calls | 1.1 | 1.9 | **6.1** |
| Typical latency | 60–130s | 60–130s | **3–18s** |

DeepSeek sustained chains of up to 10 tool calls and completed genuine
multi-step work: run tests, read the failure, edit the file, re-run, confirm.
It is roughly an order of magnitude faster than the local brains on this
hardware and far more capable at long-horizon work.

## Failures, attributed by layer

Three significant failures appeared. **None of them were the model.**

1. **DeepSeek "cannot continue after a tool result"** — PROVIDER. DeepSeek v4
   is a thinking model: it returns `reasoning_content` with a tool call and
   rejects the next request unless that is passed back. The provider was
   discarding it. Fixed inside the boundary by remembering reasoning per
   tool-call id and replaying it; Mike's history has no concept of it.
2. **DeepSeek scoring 0/3 on the benchmark** — RUNTIME. Mike dropped
   `ToolCall.call_id` when writing history, so a tool result could not be
   correlated with the call that produced it, and DeepSeek returned HTTP 400.
   `call_id` was already part of the canonical type; the runtime simply wasn't
   storing it. After the fix, DeepSeek went from 0/3 to 6/7.
3. **Gemini crashing the provider** — PROVIDER. Gemini returns a JSON *list*
   on error; `_http_error` assumed a dict and raised AttributeError while
   trying to report the failure. Now every body shape produces an error.

Each was caught because the probe and benchmark exercise the real path. Twice
in this project a provider or runtime defect has masqueraded as model
incapability — which is the entire argument for measuring rather than
assuming.

## Cost

Approximately **$0.001** across all DeepSeek probing and benchmarking
(~35k input, ~1.5k output tokens). The reported balance did not move from
$0.83, the usage being below its rounding threshold. Gemini cost nothing —
free tier, quota exhausted.

---

# Computer Runtime V2 — the local brain becomes capable

## The finding

The local brain scored 1/7 while DeepSeek scored 6/7 on the *same* runtime.
That looked conclusively like a model limitation. It was not — it was the
fourth runtime defect in this project to wear that disguise.

Two bugs in context planning, measured directly:

1. **The user's task was the first thing discarded.** Trimming worked from the
   front of the conversation, so under pressure the goal itself was dropped.
   After ten tool steps the surviving history began with an orphaned assistant
   tool call and contained no statement of what had been asked. The model was
   executing tools blind.
2. **The local brain had no room to remember anything.** Mike's prompt plus 30
   tool schemas cost ~5,300 tokens of a ~5,500 token budget at `num_ctx=8192`,
   leaving roughly 250 tokens of working headroom. Every step of an agency
   loop discarded the previous step's observations. Simulated across twelve
   steps, 24 of the model's own messages were dropped.

DeepSeek never hit either problem because its 65k window meant trimming never
engaged. The bugs were invisible to the cloud brain and fatal to the local one.

## The fixes

- The system prompt **and the first user turn** are now both pinned; the task
  can never be trimmed away.
- Trimming repairs itself: a tool result whose assistant call was dropped is
  removed rather than sent, since an orphaned result is rejected by most chat
  APIs and is uninterpretable by any model.
- `NUM_CTX` raised 8192 → 16384. Measured cost on this machine: 5.8 GB → 6.2 GB
  resident, still entirely on GPU, no latency change. Working headroom went
  from ~250 to 6,417 tokens.

None of this is Qwen-specific. Every change is in provider-neutral context
planning and benefits any brain whose window is smaller than its task.

## Result — same tasks, same runtime, local brain

| Task | before | after |
|---|---|---|
| Inspect unfamiliar repo | no | **yes** |
| Find and fix a bug | yes | **yes** (6 calls) |
| Run tests, respond to failures | no | **yes** (8 calls) |
| Modify multiple files | no | **yes** (8 calls) |
| Diagnose a failed build | no | **yes** (4 calls) |
| Recover from broken command | no | **yes** |
| Create then modify a file | no | no |
| **Verified** | **1/7** | **6/7** |

Chains of 8 tool calls are now routine locally where 1–2 was the ceiling. The
local brain is within one task of the cloud brain (6/7 vs 6/7), at roughly
10× the latency — which is the local-first trade being made deliberately.

## Benchmark harness bug fixed

The `inspect` task carried `verify: None`, patched only inside `main()`. Run
through any other entry point its verifier crashed with a TypeError and the
task was scored as failed. It is now self-contained, and the model's reply is
passed to verifiers only for the one task whose deliverable is an
explanation — every other task is still checked against real disk and process
state and ignores what the model claimed.

## Runtime V2 — verification, recovery, and two more disguised bugs

### Verification is now a first-class capability

Three read-only tools close the gap between "the tool call worked" and "the
task worked":

- `check_syntax` — does the file still parse after the edit? Demonstrated:
  `edit_file` reports success for an edit that leaves Python unparseable.
  Honest about its limits, answering "I can't check .rs files" rather than
  guessing.
- `check_port` / `check_url` — is the server actually serving? A connection
  failure is a useful answer here, and the two distinguishable cases —
  nothing listening, versus listening but not serving this request — call for
  different next steps and are reported differently.

The full lifecycle is now verifiable end to end: port empty → start → port
listening → HTTP 200 with expected content → stop → port empty again.

### Error recovery: the retry_safe flag was never consumed

The provider had been marking garbled tool calls `retry_safe=True` since the
last milestone and **nothing acted on it**, so a stochastic stumble ended the
turn. Measured on the local brain with ample context and all 33 tools
offered: **3 of 8 identical requests produced malformed tool-call XML**.

That is a genuine model limitation, not a runtime bug — but §16 says to
improve the runtime before assuming intelligence is required, and a bounded
retry is exactly that. Retried at most twice, only when the attempt produced
no text and no tool calls, so nothing is ever duplicated and a genuinely dead
backend still surfaces immediately.

Effective tool-call reliability through the real runtime went from **5/8 to
6/6**.

### A model could be silently disarmed

Under pressure from a single oversized tool result, the planner dropped
*every* tool — observed as "offering 0 of 33 tools". A model with no tools
cannot act and is told nothing about why. There is now a floor of five tools;
below it the request is refused with a clear context error instead.

### Hardware impact (8 GB machine)

| | before | after |
|---|---|---|
| `num_ctx` | 8192 | 16384 |
| Resident | 5.8 GB | 6.2 GB |
| Placement | 100% GPU | 100% GPU |
| Latency | unchanged | unchanged |
| Working headroom | ~250 tok | ~6,000 tok |

32k was measured at 6.6 GB and also viable, but 16k already provides ample
headroom, so the extra memory buys nothing on this hardware. Tools grew from
30 to 33 and still cost only 5,704 of an 11,688 token budget.

---

# Tool-call garbling: root cause

## Root cause

qwen3.5:9b ships `presence_penalty 1.5`. Mike sent only temperature, num_ctx
and num_predict, so that default applied to every request. A presence penalty
discourages tokens that have already appeared — and a tool call is *made of*
repeated structure: `<parameter=…>` … `</parameter>`, once per argument. The
penalty suppressed the closing tags, the model emitted malformed XML, and
Ollama's own parser rejected it.

## Evidence

Controlled, single-variable, Mike's real prompt and tools:

| Configuration | Failures |
|---|---|
| Mike as it was (inheriting the model's 1.5) | **7/12 (58%)** |
| `presence_penalty = 0.0` | **0/12 (0%)** |
| `presence_penalty = 1.5` (explicit control) | **7/12 (58%)** |

The failure layer was established first, before any change:

- **Ollama returns HTTP 500.** Two parsers are attempted server-side
  (`qwen3coder.go:71`, then `qwen35.go:105`) and both fail.
- **No content reaches Mike at all** — confirmed by streaming, where 5 of 10
  failing requests delivered zero bytes before the error.
- The same failure reproduces **outside Mike**, calling Ollama directly.

Effect is prompt-shaped: a call needing several `<parameter>` blocks failed
5/6 while single-argument calls did not fail in the same sample, which is
consistent with a repetition penalty and not with random corruption.

## Does an Ollama upgrade help?

**No.** Installed 0.32.3; latest 0.33.3. The upstream work that would tolerate
this corruption is **unmerged**: PR #17914 ("qwen3coder: tolerate a dropped
closing tag") — which describes our exact error — plus #16841 and #16398. No
released version contains them. Issue #17825 also reports that *retrying*
after such a 500 can hang, which is a reason to keep retry bounded.

## Did Mike contribute?

Yes. Mike did not set sampling parameters for tool requests and inherited a
prose-tuned default that is actively wrong for structured output. That is a
runtime defect, not a model defect.

## The fix

`STRUCTURED_OUTPUT_OPTIONS = {"presence_penalty": 0.0}`, applied in the Ollama
provider **only when tools are present**, so ordinary conversation keeps the
diversity the model's author intended. The reasoning is general — a repetition
penalty is wrong for any model asked to emit structured output — and nothing
branches on a model name, which a test asserts.

## Why tolerant parsing was not the answer

The brief allowed mechanically unambiguous repair at the provider boundary.
That is not possible for this failure: Ollama parses server-side and returns
500, so the malformed XML never crosses the network. Mike has nothing to
repair. Recovery must come from Ollama (the unmerged PRs) or from preventing
the corruption, which is what the sampling fix does.

## Failure rate

| | before | after |
|---|---|---|
| Provider layer, retry excluded | 58% | **8%** |
| Through the runtime, retry enabled | ~0% (masked) | ~0% (genuinely rare) |

Retry is now a fallback for residual variance rather than the mechanism
hiding a systematic defect.

---

# Reliability audit — attributing every failure

The suite had sat at "157 passed, 4 failed, 8 errors" for several milestones,
with the failures repeatedly described as pre-existing. Attributed properly,
one was a real Mike bug and the rest were tests that had drifted from the
product.

| Failure | Layer | Finding |
|---|---|---|
| `test_success_returns_description` | **MIKE** | Vision succeeded, then Mike threw the result away because a *cache write* failed. Fixed. |
| `test_clean_emojis` | test | Asserted exact equality against text that now also carries macOS `say` pause directives. The contract is that no emoji survives; it now asserts that. |
| `test_casual_message_no_see_screen_tool` | test | Pinned the literal word "explicitly" in a tool description that was later reworded. The guarantee — screen capture is user-initiated — is unchanged and is now what is asserted. |
| `test_voice_button_speaking_state` | test | Tested `ui.widgets.input.VoiceButton`, which the live app no longer references. Retargeted at the Instrument dial the controller actually drives. |
| 8 collection errors | harness | `test_vision_e2e_real.py` and `test_voice_e2e.py` are manual scripts whose steps take arguments and chain state through `__main__`. pytest read those as fixture requests. Excluded from collection, still runnable directly. |

**Result: 158 passed, 0 failed, 0 errors** — the first fully clean run. Nothing
was deleted or weakened; one product bug was fixed and four tests were
corrected to assert current intended behaviour.

## The Mike bug worth naming

`_execute_vision` performed its bookkeeping inside the same `try` as the
vision call:

```python
description = vision.describe_screen()      # succeeded
self._core.set_vision(description)          # failed -> whole thing reported as an error
```

A caching failure therefore discarded an observation the model had asked for
and already received. The cache write is now isolated, so vision reports what
it saw even if storing it fails.

## Tool-call reliability after the presence_penalty fix

Measured across four call shapes, ten attempts each, through the real
provider with Mike's real prompt and all 33 tools:

| Call shape | Valid | Parse errors | Bad arguments |
|---|---|---|---|
| two-argument search | 10/10 | 0 | 0 |
| three-argument edit | 10/10 | 0 | 0 |
| one-argument read | 10/10 | 0 | 0 |
| shell command | 10/10 | 0 | 0 |
| **Total** | **40/40 (100%)** | **0** | **0** |

Against 58% failure before the fix.

## Endurance testing — three more Mike bugs

A single long task (understand a project, find a cross-file bug, fix it, add a
function, prove both with the project's own tests) surfaced what short
benchmark tasks could not.

**First run: 1/5 objective checks.** The local brain diagnosed the bug
perfectly — its own summary read *"a 10% discount is actually being applied as
0.1%... the fix is to remove the `/ 100` from cart.py"* — and then never made
the edit. The summary ended mid-sentence, on a colon.

| Bug | Layer | Evidence |
|---|---|---|
| Generation capped at 300 tokens | **MIKE** | `done_reason="length"` at exactly 300. A model that reasons before acting spent the budget explaining and was cut off before emitting any tool call. Raised to 900, matching the OpenAI-compatible provider. Measured latency cost: none — it is a cap, not a target. |
| Truncation silently accepted | **MIKE** | Mike ignored `done_reason` entirely, so a cut-off turn was treated as a finished answer and looked like a model choosing not to act. Now detected and logged. |
| Step limit of 12 | **MIKE** | The second run reached 13 calls, made its edit on step 12, and was stopped immediately after. DeepSeek needed 13 calls for the same task. Raised to 20, still bounded. |

**Final run: 5/5, 14 tool calls, no failures, 675s.** The chain was exactly the
intended one — read, run tests, edit, re-run, edit again, `check_syntax` — and
every claim was verified against disk.

| Brain | Checks passed | Tool calls | Time |
|---|---|---|---|
| deepseek-v4-flash | 5/5 | 13 | 24s |
| qwen3.5:9b (before) | 1/5 | 10 | 777s |
| qwen3.5:9b (after) | **5/5** | 14 | 675s |

### Benchmark variance, honestly

Repeated runs give **4/7 and 6/7**, not the 7/7 reported earlier from a single
lucky run. `fixbug` failed in both of those runs and passes after the
generation-cap fix. Run-to-run variance on a local model is real and any single
figure overstates confidence.

---

# Real VS Code / computer agent test: build and improve a live web page

One high-level request, no file names, no stack, no commands. Everything about
how to do it was the model's decision. Verified against the filesystem and a
live HTTP server, never against the model's claim.

## Three Mike bugs, found in sequence

Each run failed differently, and each failure was a runtime bug rather than
the model:

1. **Generation capped at 900 tokens.** The model was cut off *mid-tool-call*
   while writing the page — so no tool call was emitted at all and the turn
   produced nothing. Measured: 900 → no call, 2000 → no call, 4000 → 12,140
   characters written.
2. **The same bug in the cloud provider.** `max_tokens` was still 900 in
   `openai_compatible.py`; raising Ollama's cap had not touched it. DeepSeek
   was being truncated identically and silently, which is why it also failed.
   Neither provider checked `finish_reason` / `done_reason`, so a cut-off
   reply was accepted as a finished answer.
3. **A flat reply reserve locked out small models.** Reserving 8k
   unconditionally made any model with a window under ~9k unusable. The
   reserve is now the smaller of the generous figure and 40% of the model's
   actual window, so a 4k model still works — it simply offers fewer tools
   (measured: 9 of 33) rather than being refused.

## Result after the fixes

| | |
|---|---|
| LLM turns | 20 |
| Tool calls | 19 |
| Distinct tools | 12 |
| Parse failures | **0** |
| Retries | **0** |
| Generation truncations | **0** |
| Context-pressure events | **0** |
| Repeated itself | no |
| Elapsed | 2,434s (~41 min) |

**Independent verification: 11/11.** HTML page exists, real CSS file, all five
sections, three projects, responsive (`@media` + viewport), structurally
complete HTML, and the site served HTTP 200 on port 3000.

The trajectory did the whole intended loop unprompted: create three files →
`check_syntax` on two → start a server → `check_port` → open the browser →
`see_screen` → `check_url` → three `edit_file` changes → re-verify.

The second-round improvement was real and driven by what it saw: it replaced
`<span>` placeholders in the project cards with inline `<svg>` artwork and
adjusted the card gradient. Both changes are present in the final files and in
the served page.

## Hardware note

The machine has **16 GB**, not the 8 GB an earlier note claimed — that stale
assumption had been making context decisions more conservative than necessary.
`qwen3.5:9b` at `num_ctx=40960` is 6.9 GB resident and still entirely on GPU.
The model's trained context is 262,144 tokens, so even this uses about 16% of
its capacity.

---

# Final runtime validation and freeze

Everything below is measured on this machine on 2026-09-05. Where a number
comes from a single run it says so, because a single run is not a rate.

## Provider architecture as it now stands

The runtime never names a backend. It holds a `BrainProvider` and speaks four
canonical types — `ToolCall`, `StreamEvent`, `ChatResult`, `BrainError` — plus
`Capabilities`, which separates what a model *declares* from what it has been
*observed* to do.

    brain/providers/base.py               canonical types, ABC, Capabilities
    brain/providers/ollama_provider.py    every Ollama-specific detail
    brain/providers/openai_compatible.py  DeepSeek / Gemini / OpenRouter
    brain/providers/__init.py__           endpoint table, get_provider()

A test now enforces the boundary directly: `done_reason` and `finish_reason`
are backend vocabulary and must not appear anywhere in `brain/core_runtime.py`.
The runtime reads the canonical `event.truncated` instead.

## Local configuration, measured

    brain / vision / summary model   qwen3.5:9b   (one model does all three)
    NUM_CTX                          40960
    resident size                    6.9 GB, 100% GPU, on a 16 GB machine
    generation cap, local            8192  (DEFAULT_NUM_PREDICT)
    generation cap, cloud            8192  (DEFAULT_MAX_TOKENS)
    usable fraction of num_ctx       0.75  (Ollama does not grant all of it)

`ollama ps` was read while a task was mid-flight, so 6.9 GB is the real
working figure rather than a cold estimate. Nothing spills to CPU at this
context size, which is what makes the local path usable at all here.

## Structured-output sampling

qwen3.5:9b ships `presence_penalty 1.5`. Applied to output that is *made of*
repeated structure (`<parameter=…>…</parameter>`), a repetition penalty
suppresses the closing tags, and Ollama's server-side parser then rejects the
result with HTTP 500. Mike sets `presence_penalty 0.0` on any request carrying
tools, and leaves ordinary conversation alone.

Measured: 7/12 tool requests failed while inheriting the penalty; 0/12 failed
with it at zero. The rule is expressed generally — "structured output should
not be penalised for repeating structure" — and a test asserts it does not
branch on a model name.

## Generation termination, now consistent

Both providers detected truncation on exactly the path the other did not:

    Ollama            streaming: logged     complete(): no check
    OpenAI-compatible streaming: no check   complete(): logged, and crashed

Since streaming is the path the runtime actually uses, cloud truncation was
invisible in normal operation. The check in `complete()` also referenced
`choices` before assignment, so every successful non-streamed cloud reply
raised `UnboundLocalError` — which is the path capability probes and
`brain_lab bench` use.

All four paths now set `truncated` on the canonical types, with identical
wording, and the runtime retries a turn that was cut off before producing
anything.

## Tool-call reliability

Across the two endurance runs on the local brain reported below, plus the
repository runs: **0 parse failures, 0 retries, 0 generation truncations.**
This is the part that is genuinely stable, and it is worth separating from
task success — reliability of the plumbing is not the same claim as the model
being able to do a job.

## Endurance results

Greenfield — build a polished landing page from an empty directory, given a
high-level request only. Two runs, both on qwen3.5:9b:

    run 1   11/11 verified   20 turns   19 tool calls   2434s
    run 2   11/11 verified   20 turns   19 tool calls   2473s

Both completed the full loop: create → serve → open → *see* → check → edit →
syntax-check → re-serve → re-verify. n=2. That is a reproduced result, not a
success rate.

Brownfield — understand, fix, run and verify a real third-party repository.
bottlepy/bottle at 3d0ace4, the genuine upstream commit before `da7e372`
("fix: Anonymous route wildcards with filter", issue #1505). The maintainers'
regression test was held out entirely and applied only after the run, and the
repository's later history was pruned so the fix commit is absent from the
object store. Mike was given the symptom in a user's words and nothing else.

    control: unfixed repository        4/8
    control: real upstream fix applied 8/8

    attempt 1   4/8   21 turns   3117s   one wrong edit, 11 regressions
    attempt 2   5/8   21 turns   1491s   correct diagnosis, no edit

Neither run fixed the bug. Attempt 1 produced an edit that swapped
`KeyError: 'anon0'` for `KeyError: None` and broke 11 of the project's 357
tests. Attempt 2 made no source edit at all but ended with an accurate
diagnosis naming the right mechanism and the right line.

**Mike is reproducibly capable on greenfield work and has not yet succeeded on
brownfield work.** Two attempts is a small sample and does not establish a
rate; it does establish that the greenfield result is not evidence for the
brownfield case.

## The 20-step boundary

`MAX_AGENT_STEPS = 20`. Both repository attempts terminated at the cap with
work outstanding, and attempt 2 held a correct diagnosis when it stopped. The
greenfield task fits in 19–20 tool calls with nothing to spare.

Where the budget went on the repository task:

    attempt 1   5 of 20 steps lost to a tool defect (see below)
    attempt 2   14 of 21 commands spent on server startup and port cleanup

The cap is doing real work as a runaway guard and has not been raised. But on
brownfield tasks it is plausibly the binding constraint rather than model
capability, and that distinction is untested — a labelled higher-cap probe is
the experiment that would settle it.

## DeepSeek control

Same harness, same task, `deepseek-v4-flash`, one run:

    10/11 verified   20-step cap reached   $0.07

Files were larger than the local model's (styles.css 19,755 B vs 7,132 B) and
it added a README. It did **not** complete the improve-and-re-verify loop: it
spent its last five steps on screenshot tooling — headless Chrome, `sips`,
display resolution, probing for PIL — and said so plainly in its own summary.
On this task the local 9B completed a loop the cloud model did not.

The one failing check was a harness defect, not the model: the port-detection
regex required `port=` or a colon, so `python3 -m http.server 8137` produced no
hint and verification probed a fixed list that did not include 8137. Mike's own
`check_url` against that port had succeeded. Fixed; the run is recorded as
10/11 with the HTTP check inconclusive, since the server had exited by the time
it could be re-checked independently.

Cost note: earlier notes in this document estimated cloud runs at ~$0.001.
Measured properly against the account balance, one endurance run is **$0.07**.

## Known model variance and limitations

- Anonymous-wildcard reasoning: attempt 1 wrote `'(?P<%s>%s)' % (key, mask)`
  inside a branch where `key` is `None` by construction. A genuine reasoning
  error, not a runtime fault.
- Server lifecycle: both the local model and DeepSeek reached first for a
  foreground `run_command` or a shell `&` instead of `run_background`. Both
  recovered, but it costs steps every time.
- Reproduction scripts encode assumptions: attempt 1's repro required its
  handler to receive a value from an *anonymous* wildcard, which upstream
  semantics never provide. Its success condition was unreachable.

## Remaining upstream Ollama limitation

Ollama parses tool-call XML server-side and returns HTTP 500 when its own
parser rejects the model's output. The malformed text never crosses the
network, so Mike cannot repair that class of corruption however tolerant its
parser is. Prevention through sampling is the available lever, and that is what
Mike does. Upstream PRs #17914, #16841 and #16398 remain unmerged.

## The pattern worth recording

Every milestone in this document has repeated the same finding: something that
looked like model incapability was a defect in Mike. The count now stands at
nine, three of them found during this final pass:

    the 900-token generation cap truncating turns mid-tool-call
    the same cap left unfixed in the cloud provider
    a flat reply reserve locking out small-context models
    num_ctx=4096 truncating the tool schemas in half
    presence_penalty inherited from the model
    vision results discarded when a cache write failed
    search_code matching regex-escaped queries literally, silently        (new)
    UnboundLocalError on every successful non-streamed cloud reply        (new)
    generation termination checked on opposite paths per provider         (new)

Three measurement defects in the test harnesses were also found, each of which
would have put a wrong number in this document: context events counted only
one of the two log prefixes and reported zero while history was being trimmed;
truncations were counted with wording that only ever matched Ollama; and the
port-detection regex above.

"The local model cannot do X" remains a hypothesis to disprove before it is a
conclusion.
