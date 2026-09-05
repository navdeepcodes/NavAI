"""Turning declared capability into observed capability.

A model card is a claim. This module is how Mike finds out what is actually
true, by exercising a brain through the real provider with Mike's real tool
schemas and recording what happened.

The distinction it enforces is three-way, not two-way:

    NOT SUPPORTED — the attempt failed, or the capability is absent
    SUPPORTED     — it worked at least once
    RELIABLE      — it worked every time it was tried

"Worked once" and "works every time" are different facts, and a brain that
tool-calls correctly half the time is not one Mike should treat as capable.

Deliberately small: a handful of short requests, so probing a metered cloud
model costs a fraction of a cent. Results are written to the same local
SQLite database as everything else, with enough context — what was tested,
when, which provider and model, and why it failed — to be worth re-reading
later.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from logs.logger import logger

_DB_DIR = Path(os.environ["MIKE_DATA_DIR"]) if os.environ.get("MIKE_DATA_DIR") \
    else Path.home() / "Library" / "Application Support" / "Mike"
_DB_PATH = _DB_DIR / "memory.db"

NOT_SUPPORTED = "not_supported"
SUPPORTED = "supported"
RELIABLE = "reliable"
# A run that never reached the model teaches nothing about the model. Rate
# limits, exhausted quota and outages must not be recorded as incapability —
# that is how a perfectly capable brain acquires a false reputation.
INCONCLUSIVE = "not_tested"

_BLOCKED_KINDS = {"unavailable", "timeout"}

# Small on purpose: enough to tell "worked once" from "works every time"
# without spending real money to learn it.
TRIALS = 2


# ══ storage ════════════════════════════════════════════════

def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS capability_observations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            provider    TEXT NOT NULL,
            model       TEXT NOT NULL,
            capability  TEXT NOT NULL,
            verdict     TEXT NOT NULL,
            passes      INTEGER NOT NULL DEFAULT 0,
            trials      INTEGER NOT NULL DEFAULT 0,
            detail      TEXT,
            latency_ms  INTEGER,
            observed_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def record(observation: "Observation", provider: str, model: str) -> None:
    _db().execute(
        "INSERT INTO capability_observations "
        "(provider, model, capability, verdict, passes, trials, detail, latency_ms, observed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (provider, model, observation.capability, observation.verdict,
         observation.passes, observation.trials, observation.detail,
         observation.latency_ms, time.time()),
    )
    _db().commit()


def history(provider: str | None = None, model: str | None = None) -> list[dict]:
    query = "SELECT * FROM capability_observations"
    conditions, params = [], []
    if provider:
        conditions.append("provider = ?")
        params.append(provider)
    if model:
        conditions.append("model = ?")
        params.append(model)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY observed_at DESC LIMIT 200"
    return [dict(r) for r in _db().execute(query, params).fetchall()]


# ══ results ════════════════════════════════════════════════

@dataclass
class Observation:
    capability: str
    verdict: str
    passes: int = 0
    trials: int = 0
    detail: str = ""
    latency_ms: int | None = None

    @property
    def ok(self) -> bool:
        return self.verdict in (SUPPORTED, RELIABLE)


@dataclass
class ProbeReport:
    provider: str
    model: str
    observations: list[Observation] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    def get(self, capability: str) -> Observation | None:
        return next((o for o in self.observations if o.capability == capability), None)

    def verdict(self, capability: str) -> str:
        found = self.get(capability)
        return found.verdict if found else "not_tested"

    def summary(self) -> str:
        rows = [f"{o.capability:22} {o.verdict:14} {o.passes}/{o.trials}"
                for o in self.observations]
        return "\n".join(rows)


# ══ the probe ══════════════════════════════════════════════

def _verdict(passes: int, trials: int, blocked: bool = False) -> str:
    if passes == 0:
        return INCONCLUSIVE if blocked else NOT_SUPPORTED
    return RELIABLE if passes == trials else SUPPORTED


# One tiny tool, so a failure means "cannot tool-call" rather than "was
# confused by thirty options".
_TINY_TOOL = [{
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Get the current time in a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
    },
}]


def probe(provider_name: str, model: str | None = None, *,
          include_vision: bool = True, image_path: str | None = None) -> ProbeReport:
    """Exercise a brain through the real provider and report what it can do."""
    from brain.providers import get_provider

    brain = get_provider(provider=provider_name, model=model, refresh=True)
    caps = brain.capabilities()
    report = ProbeReport(provider=caps.provider, model=caps.model)

    def finish(observation: Observation) -> None:
        report.observations.append(observation)
        record(observation, caps.provider, caps.model)
        logger.info("[probe] %s %s: %s (%d/%d) %s", caps.model, observation.capability,
                    observation.verdict, observation.passes, observation.trials,
                    observation.detail[:80])

    # 0. reachable at all — everything else is meaningless otherwise
    problem = brain.health()
    if problem is not None:
        finish(Observation("reachable", NOT_SUPPORTED, 0, 1, problem.human()))
        return report
    finish(Observation("reachable", RELIABLE, 1, 1))

    def track(result) -> None:
        report.input_tokens += result.input_tokens or 0
        report.output_tokens += result.output_tokens or 0

    # 1. text
    passes, detail, latency, blocked = 0, "", None, False
    for _ in range(TRIALS):
        started = time.time()
        result = brain.complete([{"role": "user", "content": "Reply with exactly: ready"}])
        latency = int((time.time() - started) * 1000)
        track(result)
        if result.error is not None:
            detail = result.error.human()
            blocked = blocked or result.error.kind in _BLOCKED_KINDS
        elif result.text.strip():
            passes += 1
        else:
            detail = "returned an empty response"
    finish(Observation("text", _verdict(passes, TRIALS, blocked), passes, TRIALS, detail, latency))

    # 2. streaming — text must arrive in more than one piece to count
    passes, detail, blocked = 0, "", False
    for _ in range(TRIALS):
        chunks, failed = 0, None
        for event in brain.stream([{"role": "user", "content": "Count: one two three four"}]):
            if event.kind == "text" and event.text:
                chunks += 1
            elif event.kind == "error":
                failed = event.error.human()
                blocked = blocked or event.error.kind in _BLOCKED_KINDS
        if failed:
            detail = failed
        elif chunks > 1:
            passes += 1
        else:
            detail = f"only {chunks} chunk(s) — not genuinely streamed"
    finish(Observation("streaming", _verdict(passes, TRIALS, blocked), passes, TRIALS, detail))

    # 3. a single simple tool call
    passes, detail, blocked = 0, "", False
    for _ in range(TRIALS):
        result = brain.complete(
            [{"role": "user", "content": "What time is it in Tokyo? Use the tool."}],
            _TINY_TOOL,
        )
        track(result)
        if result.error is not None:
            detail = result.error.human()
            blocked = blocked or result.error.kind in _BLOCKED_KINDS
        elif result.tool_calls and result.tool_calls[0].name == "get_time":
            if isinstance(result.tool_calls[0].arguments, dict):
                passes += 1
            else:
                detail = "arguments did not normalise to a dict"
        else:
            detail = "did not call the tool"
    finish(Observation("tool_calling", _verdict(passes, TRIALS, blocked), passes, TRIALS, detail))

    # 4. Mike's real tool schemas — 30 of them, the realistic condition
    from brain.context_budget import plan_request
    from brain.core_runtime import SYSTEM_PROMPT
    from brain.core_tools import OLLAMA_TOOLS, check_arguments

    passes, detail, blocked = 0, "", False
    for _ in range(TRIALS):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.replace("{date}", "today")},
            {"role": "user", "content": "Find where get_conn is used in /tmp/proj."},
        ]
        plan = plan_request(messages, OLLAMA_TOOLS, caps)
        if not plan.fits:
            detail = plan.error.human()
            break
        result = brain.complete(plan.messages, plan.tools)
        track(result)
        if result.error is not None:
            detail = result.error.human()
            blocked = blocked or result.error.kind in _BLOCKED_KINDS
        elif not result.tool_calls:
            detail = "made no tool call with Mike's real schemas"
        else:
            call = result.tool_calls[0]
            problem = check_arguments(call.name, call.arguments)
            if problem:
                detail = f"invalid arguments: {problem[:120]}"
            else:
                passes += 1
    finish(Observation("mike_tools", _verdict(passes, TRIALS, blocked), passes, TRIALS, detail))

    # 5. continuing after a tool result — the behaviour agency depends on
    passes, detail, blocked = 0, "", False
    for _ in range(TRIALS):
        # A real round-trip: let the model make the call, then hand back the
        # result using the id it actually issued. A synthetic id would fail
        # for reasons that have nothing to do with the model's ability to
        # continue — which is exactly the sort of false negative this probe
        # exists to avoid.
        opening = {"role": "user", "content": "What time is it in Tokyo? Use the tool."}
        first = brain.complete([opening], _TINY_TOOL)
        track(first)
        if first.error is not None or not first.tool_calls:
            detail = first.error.human() if first.error else "made no initial tool call"
            if first.error is not None:
                blocked = blocked or first.error.kind in _BLOCKED_KINDS
            continue
        call = first.tool_calls[0]
        conversation = [
            opening,
            {"role": "assistant", "content": first.text,
             "tool_calls": [{"id": call.call_id or "call_0",
                             "function": {"name": call.name, "arguments": call.arguments}}]},
            {"role": "tool", "tool_call_id": call.call_id or "call_0",
             "content": json.dumps({"time": "14:05"})},
        ]
        result = brain.complete(conversation, _TINY_TOOL)
        track(result)
        if result.error is not None:
            detail = result.error.human()
            blocked = blocked or result.error.kind in _BLOCKED_KINDS
        elif "14:05" in result.text or "14" in result.text:
            passes += 1
        elif result.text.strip():
            passes += 1
            detail = "continued, though without quoting the result"
        else:
            detail = "did not continue after the tool result"
    finish(Observation("tool_continuation", _verdict(passes, TRIALS, blocked), passes, TRIALS, detail))

    # 6. a nonsense tool request must be refused, never executed
    bad = brain.normalise_arguments("this is not json")
    finish(Observation(
        "rejects_malformed", RELIABLE if bad[1] else NOT_SUPPORTED, 1, 1,
        bad[1] or "malformed arguments were accepted, which is unsafe",
    ))

    # 7. vision
    if include_vision:
        if not caps.can("vision"):
            finish(Observation("vision", NOT_SUPPORTED, 0, 0,
                               "the model does not declare image input"))
        elif not image_path or not Path(image_path).exists():
            finish(Observation("vision", "not_tested", 0, 0, "no probe image supplied"))
        else:
            passes, detail, blocked = 0, "", False
            for _ in range(TRIALS):
                text, error = brain.describe_image(
                    image_path, "What error is shown? Name the file and line."
                )
                if error is not None:
                    detail = error.human()
                    blocked = blocked or error.kind in _BLOCKED_KINDS
                elif "checkout" in text.lower() or "42" in text:
                    passes += 1
                elif text.strip():
                    detail = "described the image but missed the detail asked for"
                else:
                    detail = "returned nothing"
            finish(Observation("vision", _verdict(passes, TRIALS, blocked), passes, TRIALS, detail))

    # Write the evidence back onto the provider's capability profile, which is
    # the whole point: from here on, can() answers from observation.
    if hasattr(brain, "record_observation"):
        brain.record_observation(
            observed_tools=report.get("mike_tools").ok if report.get("mike_tools") else None,
            observed_streaming=report.get("streaming").ok if report.get("streaming") else None,
            observed_vision=report.get("vision").ok if report.get("vision") else None,
        )

    return report
