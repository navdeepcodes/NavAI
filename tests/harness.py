"""Shared instrumentation for the real-agent runs.

Every endurance script needs the same things: a record of what the agent
actually called, how long each call took, which calls failed and whether it
recovered, and a way to stand in for the user at a confirmation. Written once
here so the benchmark table for one task is measured the same way as for
every other, and so a script is about its task rather than about plumbing.

Nothing here decides what the agent should do, and nothing reads the model's
prose to judge success. Verification is always a function the caller supplies
that inspects real state.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MIKE_DATA_DIR", str(Path.home() / ".mike-brain-lab"))

# Tools whose cost is dominated by the vision model rather than by the OS.
VISION_TOOLS = frozenset({"see_screen"})


@dataclass
class Call:
    n: int
    tool: str
    args: dict
    status: str
    ms: int
    detail: str


@dataclass
class Run:
    task: str
    brain: str
    seconds: int
    turns: int
    calls: list[Call] = field(default_factory=list)
    confirmations: list[dict] = field(default_factory=list)
    reply: str = ""
    stopped_early: str = ""
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    # ── metrics for the benchmark table ───────────────────

    @property
    def failed_calls(self) -> list[Call]:
        return [c for c in self.calls if c.status not in ("success", "command_failed")]

    @property
    def vision_calls(self) -> int:
        return sum(1 for c in self.calls if c.tool in VISION_TOOLS)

    @property
    def recoveries(self) -> int:
        """A failed call the agent came back from: it called the same tool
        again later and that call succeeded. Counting this rather than raw
        failures is the honest measure — a tool erroring is only a problem if
        the agent then gives up or lies about it."""
        recovered = 0
        for index, call in enumerate(self.calls):
            if call.status in ("success", "command_failed"):
                continue
            if any(later.tool == call.tool and later.status == "success"
                   for later in self.calls[index + 1:]):
                recovered += 1
        return recovered

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(ok for _, ok, _ in self.checks)

    @property
    def verification(self) -> str:
        passed = sum(1 for _, ok, _ in self.checks if ok)
        return f"{passed}/{len(self.checks)}"

    def as_row(self, label: str, run_number: int) -> str:
        result = "PASS" if self.passed else "FAIL"
        return (
            f"| {label} | {run_number} | {result} | {self.turns} | {len(self.calls)} "
            f"| {self.seconds}s | {self.vision_calls} | {self.recoveries} "
            f"| {self.verification} |"
        )

    def to_dict(self) -> dict:
        return {
            "task": self.task[:400], "brain": self.brain, "seconds": self.seconds,
            "turns": self.turns, "stopped_early": self.stopped_early,
            "calls": [c.__dict__ for c in self.calls],
            "confirmations": self.confirmations,
            "checks": [{"check": n, "passed": ok, "detail": d}
                       for n, ok, d in self.checks],
            "reply": self.reply[-1500:],
        }


TABLE_HEADER = (
    "| Task | Run | Result | Turns | Calls | Time | Vision | Recovery | Verification |\n"
    "|---|---:|---|---:|---:|---:|---:|---:|---|"
)


def run_agent(
    task: str,
    *,
    confirm=None,
    steps: int | None = None,
    time_budget: int = 1800,
    runtime=None,
    echo: bool = True,
) -> Run:
    """Run one real task through the real runtime and record everything.

    `confirm` receives (detail, tool_name, args) and returns True/False, so a
    caller can judge the actual arguments rather than a description of them —
    a stand-in that rubber-stamps proves nothing about the gate.
    """
    import brain.core_runtime as core_runtime
    from brain.core_runtime import CoreRuntime

    if steps:
        core_runtime.MAX_AGENT_STEPS = steps

    runtime = runtime or CoreRuntime()
    brain = runtime._brain_capabilities().model

    calls: list[Call] = []
    original_execute = runtime._execute_tool

    def recording(name, tool_args):
        started = time.time()
        result = original_execute(name, tool_args)
        payload = result if isinstance(result, dict) else {}
        calls.append(Call(
            n=len(calls) + 1,
            tool=name,
            args={k: str(v)[:160] for k, v in (tool_args or {}).items()},
            status=payload.get("status", "?"),
            ms=round((time.time() - started) * 1000),
            detail=str(payload.get("result") or payload.get("error") or "")[:400],
        ))
        if echo:
            mark = "ok " if calls[-1].status == "success" else "ERR"
            print(f"       {mark} {calls[-1].detail[:100]}", flush=True)
        return result

    runtime._execute_tool = recording

    turns = [0]
    original_loop = runtime._streaming_loop

    def counting(cb, ce, depth=0):
        turns[0] += 1
        yield from original_loop(cb, ce, depth)

    runtime._streaming_loop = counting

    # The confirmation callback is handed a description, not the arguments, so
    # the arguments are captured on the way past the gate.
    pending: dict = {"tool": "", "args": {}}
    original_needs = core_runtime.needs_confirmation

    def watching(name, tool_args):
        decision = original_needs(name, tool_args)
        if decision:
            pending["tool"] = name
            pending["args"] = tool_args or {}
        return decision

    core_runtime.needs_confirmation = watching

    confirmations: list[dict] = []

    def gate(detail: str) -> bool:
        allowed = True if confirm is None else bool(
            confirm(detail, pending["tool"], pending["args"])
        )
        confirmations.append({
            "tool": pending["tool"],
            "args": {k: str(v)[:200] for k, v in pending["args"].items()},
            "detail": str(detail)[:600],
            "allowed": allowed,
            "at_call": len(calls),
        })
        if echo:
            print("\n  >> CONFIRMATION")
            for line in str(detail).splitlines():
                print(f"     {line}")
            print(f"     -> {'ALLOW' if allowed else 'DENY'}\n", flush=True)
        return allowed

    started = time.time()
    reply, stopped = "", ""
    try:
        for kind, payload in runtime.process_streaming(task, confirm_callback=gate):
            if kind == "token":
                reply += payload
            elif kind == "tool_start" and echo:
                print(f"  [{len(calls) + 1:2}] {payload[:74]}", flush=True)
            if time.time() - started > time_budget:
                stopped = "exceeded the time budget"
                break
    except Exception as exc:
        stopped = f"{type(exc).__name__}: {exc}"
    finally:
        core_runtime.needs_confirmation = original_needs

    return Run(
        task=task, brain=brain, seconds=round(time.time() - started),
        turns=turns[0], calls=calls, confirmations=confirmations,
        reply=reply, stopped_early=stopped,
    )


def report(run: Run, title: str) -> None:
    print(f"\n--- {title}: verification ({run.verification}) ---")
    for name, ok, detail in run.checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")
    print(
        f"\nturns: {run.turns}  calls: {len(run.calls)}  failed: "
        f"{len(run.failed_calls)}  recovered: {run.recoveries}  "
        f"vision: {run.vision_calls}  time: {run.seconds}s"
    )
    if run.stopped_early:
        print(f"stopped early: {run.stopped_early}")
    print(f"model's own summary: {run.reply.strip()[-260:]!r}")


def save(run: Run, name: str) -> Path:
    import json

    out = Path(__file__).parent.parent / "design" / "evidence" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run.to_dict(), indent=2, default=str))
    print(f"evidence: {out}")
    return out
