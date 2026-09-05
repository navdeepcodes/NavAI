# Structured data, arithmetic, and whether the capabilities compose

Written during Phase 2 hardening. Everything here came out of running the
real runtime against real files and a real mailbox, and every claim below has
a test or an evidence file behind it.

---

## 1. Why a spreadsheet is not a document

`read_document` already turned a spreadsheet into prose, and that is the
right answer to "what does this file say". It is the wrong answer to "put
4820 in C5", because prose has no cell addresses.

So spreadsheets are not a new kind of file here, they are a second *view* of
one: `read_spreadsheet` returns an addressed grid, and `edit_spreadsheet`
sets cells by address. Two operations, because a grid only supports two —
look at it, and change part of it. No `SheetsAgent`, no workflow object, no
per-application special case; the model composes these with everything else
it has exactly as it composes `read_file` with `write_file`.

Formats are `.xlsx`/`.xlsm` through openpyxl and `.csv` through the standard
library. Apple's `.numbers` is a proprietary bundle nothing here can parse,
and it is refused by name.

### The two honesty constraints

**Mike cannot calculate a formula.** openpyxl stores `=SUM(C2:C5)` as a
string and never evaluates it, and a workbook Mike wrote carries no cached
result for any formula in it. The dangerous version of this capability writes
that formula and then tells the user the total is 8,040. So a formula with no
stored value is reported as *not calculated*, in the grid and in a note, and
the note says where the real number can be got.

This is not theoretical caution. On the cross-application run, the model
wrote `=SUM(C2:C6)`, read the sheet back, saw `(not calculated)`, worked the
number out and replaced the formula with `9304`. The honesty note is what
produced the correct file.

Confirmed against a real spreadsheet application: opening a workbook Mike
wrote in Apple Numbers shows the formula evaluating to exactly the literal
Mike had calculated. Mike's formulas are valid; Mike's inability to evaluate
them is Mike's limit, not a broken file.
(`design/evidence/spreadsheet_formula_computed_by_numbers.png`)

**A save is not a write.** `wb.save()` returning means openpyxl did not
raise. The file is reopened and every requested cell checked before success
is reported, and every mismatch is listed rather than the first one.

### Two bugs the verification found

*Numeric text.* A model producing JSON writes `"60"` far more often than
`60`. Stored as text, it makes every `SUM` below it silently return zero —
the worst kind of wrong, because the sheet looks fine. Values that convert
losslessly are stored as numbers; `Widget` and `=SUM(...)` are left alone.

*Empty is absent.* An agent wrote `""` into a cell to leave it blank, which
is correct, and the verification reported the write as failed because the
cell read back as `None`. Empty and absent are the same thing in a
spreadsheet. Seen live; cost the agent a step recovering from a problem that
did not exist.

---

## 2. An unreadable file is only a dead end if nothing else is named

Given a `.numbers` document with an `.xlsx` export sitting beside it, Mike
refused the `.numbers` correctly, did not invent any figures, opened Numbers,
and asked the user to export a file **that already existed**. The model
behaved sensibly on the information it had. The information was incomplete.

The unsupported-format error now names the files in the same folder that Mike
*can* open. Re-run, the same task recovered without asking: it read the
error, listed the folder, opened the export and finished. The tool supplies
the fact; the model still decides what to do with it.

Ninth or tenth time this pattern has appeared in this project. The habit it
enforces: before concluding a model cannot do something, check what it was
actually told.

---

## 3. Arithmetic

The long-horizon run read six workbooks correctly, wrote every cell
correctly, and held its goal across fifteen turns without drifting — and
totalled `2417 + 3168 + 912` as **6500** instead of 6497 on the first
workbook, then carried that figure into the summary consistently enough that
it read as deliberate. Nothing in the runtime could catch it, because nothing
in the runtime could add.

`calculate` evaluates an expression and returns the number. It decides
nothing and sequences nothing; the model chooses when a figure matters, the
same way it chooses when to read a file. It is not `eval` — the expression is
parsed to an AST and walked against a whitelist, so a string arriving from a
model, or from a document a model read, cannot reach an attribute, a name, or
any call but `sum`, `min`, `max`, `abs`, `round`, `sqrt`, `floor`, `ceil`.

**What it did and did not fix, measured.** On the re-run the model used
`calculate` for the combined six-region total and got it right for its
inputs — and still did the six per-workbook sums in its head, repeating the
identical 6497 → 6500 error. The tool closes the gap where the model reaches
for it. It does not decide for the model, and it has not been made to: a
runtime that intercepted arithmetic would be hiding exactly the variance
worth seeing.

---

## 4. Do the capabilities compose?

The question the individual capability tests cannot answer. One task,
nothing sequenced, ordinary tool set:

> read the late figures out of a text file, add them to the workbook, total
> everything, save, email the workbook to a person, attach it

Result, first attempt, 11 of 11 checks: `filesystem -> spreadsheet -> gmail`,
7 turns, 7 calls, 162 seconds, one recovered failure, two confirmations
(the file change and the send), both judged against real arguments rather
than rubber-stamped.

The last check is the one that matters. The attachment was **downloaded back
out of Gmail and opened as a workbook**, and the total Mike calculated was
read from the bytes Google stored. Not the model's summary, not the returned
message id, not the file on disk — the file the recipient will actually open.

---

## 5. Long-horizon behaviour, measured rather than assumed

Six workbooks to read, total and write, then a summary depending on figures
gathered at the very start — chosen so that context growth, history trimming,
state loss, repetition and the step limit each had somewhere to show
themselves.

| | run 1 | run 2 |
|---|---|---|
| turns | 15 | 16 |
| tool calls | 14 | 15 |
| first request | 7,798 tokens | ~7,800 tokens |
| largest request | 10,846 tokens | ~11,300 tokens |
| budget | 22,528 tokens | 22,528 tokens |
| peak use of budget | 48% | 50% |
| history messages dropped | 0 | 0 |
| tools dropped | 0 | 0 |
| identical calls repeated | none | none |
| step limit reached | no | no |
| goal held to the end | yes | yes |

**The existing architecture is sufficient at this length, and no checkpoint
mechanism was added.** Adding state-preservation machinery here would have
been solving a problem the measurements say does not exist yet.

The reason it holds is already in `context_budget.py`: the system prompt and
the *first user turn* are pinned and never dropped, so the goal cannot be
trimmed away; history goes oldest-first; orphaned tool results are repaired
rather than sent; and the tool surface has a floor below which the request is
refused loudly instead of quietly disarmed.

**Where the limit actually is.** At 50% of budget after fifteen turns, the
same shape of task would meet trimming somewhere around thirty turns, and
`MAX_AGENT_STEPS = 20` stops the run before that. So the step limit is the
binding constraint, not the context window — which is the right way round: a
bounded run that reports honestly beats an unbounded one that drifts. Raising
the step limit without re-measuring would move the binding constraint to
trimming, and that is where state loss would first become possible.

The one defect at this length is arithmetic, covered above. It is not a
long-horizon failure — it happened on the first workbook, in the second
minute.

---

## 6. Memory deletion

`forget_memory` was the last destructive tool that ran without asking.
Everything else that cannot be undone — writing over a file, deleting a path,
running a command, sending mail — stops for the user. Memory did not, so
"forget everything" reached the database on the model's say-so, with no undo
and no copy on disk.

Saving and recalling stay ungated; a confirmation that fires on harmless
operations is one the user learns to click through. Deleting now stops, and
the prompt is built **from the database by the same selector that does the
deleting** — the user sees the actual rows at risk, not a restatement of the
request. A preview computed by separate logic could describe one set and
delete another, which is the failure a confirmation exists to prevent.

Deletion is verified by re-running the selector after the delete and
requiring it to come back empty. `rowcount` is the driver describing its own
work; this reads the stored state.

A standing test now sweeps every declared tool for destructive wording and
fails if one is ungated, with a short explicit list of the justified
exceptions — so the next one cannot slip in unnoticed.

---

## 7. Voice and background lifecycle under stress

Previously inherited rather than stressed. Now: five full window
startup/teardown cycles with thread counting either side, twenty hide/show
cycles, ten wake-word start/stop cycles, ten recorder cycles, twenty
speak/stop cycles checked for orphaned `say` processes, real barge-in
(interrupting mid-utterance and confirming the process is gone), and real
speech recognition on audio generated for the test.

The finding: **an optional background service failing at startup stopped Mike
from opening at all.** The IDE bridge handles the failure it expects — a
taken port returns False — but anything unexpected propagated out of
`MikeWindow.__init__`. Losing a hotkey is an inconvenience; losing Mike
because of a hotkey is not a trade worth making. Optional services now start
through a helper that logs and steps over an unexpected failure. Deliberately
not applied to the runtime, controller or page: those *are* Mike, and a
window without them would be a shell pretending to work.

Failure isolation is now pinned from the other side too — a dead microphone,
a missing `say` binary and a wake-word callback that raises all leave the
core runtime answering.

---

## 8. What the repeated runs found

Thirteen real agent runs across four tasks. Two failures, both real, both
traced, neither hidden.

**A recoverable error that could not recover.** Spreadsheet run 3 ended in
eleven seconds with one turn, zero tool calls, and the reply *"I'll open the
spreadsheet and work through this step by step. qwen3.5:9b produced a tool
call the server couldn't parse."*

The provider had marked that failure retry-safe. The runtime declined to
retry it, because of this rule:

```python
produced_nothing = not collected_text and not tool_calls_raw
recoverable = (... .retry_safe or truncated) and produced_nothing and ...
```

The rule is right for a truncated turn, where the text so far may be a real
partial answer worth not duplicating. It was wrong for a parse failure — and
because models write a sentence before they call a tool, *that sentence
counted as output*, so the retry path was dead for the case that actually
happens. A parse failure means the tool call never parsed: nothing ran, and
nothing can happen twice.

Now a protocol failure with no parsed tool calls is retried even after a
preamble. The cost is that a reader may see that sentence twice; the cost of
the old rule was the task. The existing retry test emitted no text at all,
which is exactly why this was invisible for so long — the new tests emit the
preamble, and pin the truncation guarantee separately so it cannot be traded
away.

**A defect in the measuring instrument.** The re-run failed again, and this
time Mike was blameless: it read the workbook, used `calculate` and got 9304
right, and asked permission with exactly the right cells. The stand-in user
refused, because it compared paths as strings and the model had written
`Q3_sales.xlsx` where the file is `q3_sales.xlsx` — the same file on a
case-insensitive filesystem. The check now asks the filesystem with
`samefile` instead of guessing.

Worth recording plainly: a benchmark harness can fail a run the system got
right, and if it had not been investigated it would have been written up as a
model failure. That is the same mistake as blaming the model for a tool bug,
pointed the other way.

### The table

| Task | Runs | Passed | Turns | Calls | Time | Vision |
|---|---|---|---|---|---|---|
| browser form | 3 | 3 | 15–17 | 14–16 | 413–583s | 0 |
| email | 3 | 3 | 4–5 | 3–4 | 62–82s | 0 |
| spreadsheet | 3 (+1 rerun) | 3 | 7–8 | 6–7 | 137–166s | 0 |
| cross-application | 3 | 3 | 7 | 7–8 | 192–218s | 0 |

**Zero vision calls across all thirteen runs.** Every task — including
filling a web form in Safari — was completed through the accessibility tree
alone. The 4–7 second vision fallback exists and is tested, and on this
workload it was never needed.
