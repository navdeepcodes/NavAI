# Known Limitations

## Local model does not reliably invoke `calculate` for trivial arithmetic

**Reproduction:** `CoreRuntime.process_streaming("What is 3 + 3?")` on qwen3.5:9b
returns the literal token "4" with zero tool calls, 100% reproducible across
repeated runs (confirmed 2026-09-06).

**Impact:** Any arithmetic the model judges "too simple to need a tool" can be
silently wrong. The `calculate` tool itself is correct in every case tested
directly (3+3=6, 15+27=42, 7*8=56); the failure is purely non-invocation.

**Likely cause:** The system prompt (brain/core_runtime.py) instructs the model
to use `calculate` for arithmetic "that matters," with examples oriented
around report-style totals. The model appears to categorize single-digit or
very simple arithmetic as not meeting that bar. Strengthening the instruction
to explicitly name trivial cases ("this includes small, simple-looking sums
like 3 + 3") was tested and did NOT change the observed behavior — this
appears to be a capability/compliance limit of the 9B local model rather than
a wording problem.

**Safest next step:** Forcing all arithmetic through `calculate` regardless of
model judgment (e.g. detecting numeric patterns and requiring the tool) would
fix this but is a real architecture decision — trading "trust the model's tool
judgment" for "force specific patterns" — and risks false positives on
non-arithmetic numeric text. This should be a deliberate, reviewed change, not
a side effect of a reliability pass. Options to evaluate separately: (a) a
narrowly-scoped pre-flight check that only fires on a very high-confidence
bare-arithmetic pattern ("What is N [+-*/] N") and injects a calculate result
into context before the model replies, or (b) accepting this as a known
accuracy ceiling of the current local model and revisiting if/when a larger
or more tool-compliant local model is adopted.
