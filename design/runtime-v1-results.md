# Computer + Project Runtime V1 — results

Companion to `design/mike-professional-product-blueprint.md`. Raw per-task
records: `design/benchmark_results.json`.

## The headline

| Measure | Result |
|---|---|
| End-to-end benchmark (runtime + qwen3:8b) | **1 / 10 verified** |
| Substrate capability (runtime driven correctly) | **8 / 8 verified** |
| Tasks that ended after ≤2 tool calls | **10 / 10** |
| LLM turns granted by runtime vs. tool calls model used | **3 vs 2** (measured) |

Those four rows are the whole finding. The substrate completes every
benchmark task when driven correctly. The end-to-end number is low because
the model performs one observation, narrates it, and stops — while the
runtime is still offering it turns.

## Per-task benchmark results

| Task | Tools used | Calls | Claimed | Verified | Objective evidence |
|---|---|---|---|---|---|
| Inspect unfamiliar repo | project_overview | 1 | yes | **yes** | answer contained repo-only facts: inventory-api, express, jest |
| Find and fix a bug | project_overview, project_tree | 2 | no | no | pytest exit=1; `add()` still `return a - b` |
| Run tests, respond to failures | read_lines | 1 | no | no | pytest exit=1 |
| Modify multiple files | multi_edit | 1 | no | no | all 3 files still contain `get_conn` |
| Diagnose failed build | read_lines | 1 | **yes** | no | build exit=1, config.json still invalid — **overclaim** |
| Start dev server, verify | run_background | 1 | no | no | connection refused on port |
| Build a small website | (none) | 0 | no | no | no .html created |
| Recover from broken command | run_command | 1 | no | no | output.txt never created |
| Create then modify file | write_file | 1 | no | no | notes.txt not created |
| General task outside a repo | read_file | 1 | no | no | no summary file created |

One overclaim caught (`build`) — the model said it fixed the build while
`config.json` was still invalid JSON and the build still exited 1. Catching
that is precisely what the claimed/verified split exists for.

## Substrate capability results

Same tasks, same `CoreRuntime._execute_tool` path, same objective verifiers —
driven with the tool calls a competent model would emit:

| Capability | Verified |
|---|---|
| Fix a bug and prove it (run → observe failure → read → edit → re-run) | pytest exit=0 |
| Diagnose and fix a build | BUILD_OK, config.json valid |
| Multi-file rename | 3/3 files renamed, 0 stale references |
| Start and verify a server | HTTP 200, expected body |
| Recover from broken command | output.txt correct |
| Inspect unfamiliar repo | every needed fact in one call |
| Create then modify without data loss | both lines present |
| Missing-path error names directory contents | jan.txt, feb.txt reported |

8/8.

## Why the tool calls failed (all model-side, all reported clearly)

Every non-success call in the benchmark was a malformed request, and in every
case the runtime returned an actionable message:

- `read_lines` on a directory → "is a directory, not a file"
- `multi_edit` on a directory → could not read
- `run_background` → exit 127, command not found
- `write_file` with `text=` instead of `content=` → names the missing
  parameter, lists accepted ones, states nothing ran and retry is safe
- `read_file` with a glob `receipts/*` → "does not exist. …/receipts contains:
  feb.txt, jan.txt, notes.md"

The model read these correctly (in one run it restated the `content` fix
verbatim) and still chose to ask the user rather than retry.

## Model limitations (qwen3:8b)

1. **Does not sustain multi-step goals.** Ends after one observation with
   "Let me know if you need further assistance." Measured directly: runtime
   granted 3 turns, model used 2.
2. **Does not retry after a recoverable, clearly-explained error.**
3. **Narrates instead of acting** — reads a build script and explains what it
   does rather than running it.
4. **Occasionally emits nothing at all** (website task: 0 tool calls, empty
   reply).
5. **Overclaims** — asserts a fix that did not happen.

None of these are addressable by the runtime without building exactly the
deterministic planner the milestone forbids.

## Runtime limitations still present

1. **`write_file` vs `ide_apply_edit` parameter mismatch** (`content` vs
   `text`) — a real inconsistency that invites the error seen above.
   Harmonising them is a small, worthwhile change.
2. **An empty model turn produces nothing** — no tool calls, no text, no
   surfaced explanation.
3. **No syntax/format validation after an edit.** `edit_file` guarantees the
   text changed, not that the file still parses.
4. **No git-specific tools.** Reachable via `run_command`, but a
   `git_diff`/`git_status` pair would be cheaper than shelling out.
5. **Browser is navigate-only** — open a URL, no DOM inspection or
   interaction, so "inspect the running website visually and correct an
   issue" is not achievable end-to-end. Vision can screenshot the screen, not
   a specific page.
6. **`search_files` is now redundant** with `search_code` and defaults to
   Desktop; worth removing to stop the model choosing the weaker one.
7. **Benchmark grading of "claimed" is a keyword heuristic** — adequate for
   spotting overclaims, not rigorous.
8. **`run_command` with no `cwd` runs in Mike's own source directory.**
   Observed for real: the `recover` benchmark task omitted `cwd`, so
   `cat missing_file.txt > output.txt` created a stray file in the Mike repo
   root. Nothing was damaged and the file has been removed, but the default
   is wrong — a command with no stated working directory should not land in
   the application's own tree. This is the first concrete case where the
   deferred filesystem-scoping work has a direct effect on the runtime, and
   it is the single most important follow-up.

## Two bugs the benchmark caught

- **Fixture bug (mine):** `build.sh` had no `set -e`, so `echo BUILD_OK` ran
  after the failing step and the script exited 0 — the "failing build" never
  failed. Fixed.
- **Real verification trap:** a same-length edit within the same second
  (`a - b` → `a + b`) leaves CPython's `.pyc` cache valid, because
  invalidation compares only integer-second mtime and size. Tests then report
  the *old* behaviour immediately after a correct fix — a false negative at
  the exact moment verification matters most. `edit_file`/`multi_edit` now
  nudge mtime forward when it would otherwise collide.
