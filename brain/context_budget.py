"""Deciding what fits in a request, before it is sent.

This exists because of a real failure. Mike sent a ~4,950-token prompt with a
4,096-token context budget; Ollama silently truncated the input to 2,050
tokens, which cut the tool schemas in half. The model then invented argument
names (`text` for `content`, `directory` for `cwd`) and, with a stricter
parser, emitted tool-call syntax the server rejected outright. Every symptom
pointed at the model. The cause was the request.

The rule that follows: tool schemas are never truncated. A model holding half
a tool definition will call that tool wrongly, and a wrong tool call is worse
than no tool call. When something has to give, it is conversation history
first, then supplementary context, then the number of tools offered — and if
even a minimal request cannot fit, the request fails loudly instead of being
quietly mangled.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from brain.providers.base import BrainError, Capabilities, estimate_tokens
from logs.logger import logger

# Room left for the model's own reply plus estimation error. The estimator is
# deliberately approximate, so this is the margin that keeps an approximate
# answer safe.
# Room left for the model's own reply. It has to cover the largest reply the
# model may generate, not a typical one: authoring a file is a single tool
# call carrying the whole file in its arguments, and if too little is left the
# call is cut off mid-argument and the turn produces nothing.
#
# But it cannot be a flat figure. Reserving 8k unconditionally makes any model
# with a window under ~9k unusable, which is the wrong answer for a small
# local model — such a model should still work, it simply cannot write a huge
# file in one call. So the reserve is the smaller of the generous figure and a
# share of what the model actually has.
RESERVED_FOR_REPLY = 8192

# Never give up more than this share of a model's window to reply headroom;
# below it there would be no room left to think with.
MAX_RESERVE_FRACTION = 0.4

# Below this there is no point sending anything at all — a system prompt and
# a single user message will not fit, and pretending otherwise produces the
# exact silent corruption this module exists to stop.
MINIMUM_WORKABLE_INPUT = 1200

# Fewer tools than this and the model cannot meaningfully operate a computer,
# so the request is refused instead of being sent in a disarmed state.
MINIMUM_TOOLS_OFFERED = 5


@dataclass
class RequestPlan:
    """What should actually be sent, and what had to be dropped to fit."""

    messages: list[dict]
    tools: list[dict] | None
    estimated_tokens: int
    budget: int
    dropped_history: int = 0
    dropped_tools: int = 0
    notes: list[str] = field(default_factory=list)
    error: BrainError | None = None

    @property
    def fits(self) -> bool:
        return self.error is None


def plan_request(
    messages: list[dict],
    tools: list[dict] | None,
    capabilities: Capabilities,
    *,
    reserved: int = RESERVED_FOR_REPLY,
) -> RequestPlan:
    """Fit a request to the brain's real input budget.

    `messages` is assumed to be [system, ...conversation] with the most
    recent turns last. The system message and the most recent user turn are
    never dropped: without them the model has no instructions and no task.
    """
    reserved = min(reserved, int(capabilities.max_input_tokens * MAX_RESERVE_FRACTION))
    budget = max(0, capabilities.max_input_tokens - reserved)
    tools = list(tools) if tools else None

    if budget < MINIMUM_WORKABLE_INPUT:
        return RequestPlan(
            messages=messages,
            tools=tools,
            estimated_tokens=0,
            budget=budget,
            error=BrainError(
                kind="context",
                message=(
                    f"{capabilities.model} only allows about "
                    f"{capabilities.max_input_tokens:,} tokens per request, which "
                    "is too small for Mike to work with."
                ),
                detail=f"usable budget after reply headroom: {budget}",
            ),
        )

    system = messages[0] if messages and messages[0].get("role") == "system" else None
    rest = messages[1:] if system else list(messages)

    # The first user turn is the task. Dropping it leaves the model running
    # tool calls with no idea what it was asked to do — measured directly:
    # under pressure the surviving history began with an orphaned assistant
    # tool call and the goal was gone. It is pinned alongside the system
    # prompt for the same reason: without either, the request is meaningless.
    anchor = None
    if rest and rest[0].get("role") == "user":
        anchor = rest[0]
        rest = rest[1:]

    fixed = estimate_tokens(system) if system else 0
    fixed += estimate_tokens(anchor) if anchor else 0
    tools_cost = estimate_tokens(tools) if tools else 0
    notes: list[str] = []
    dropped_history = 0
    dropped_tools = 0

    def _assemble(kept: list[dict]) -> list[dict]:
        out: list[dict] = []
        if system:
            out.append(system)
        if anchor:
            out.append(anchor)
        out.extend(kept)
        return out

    # 1. Trim the oldest exchanges, keeping the most recent — those carry what
    #    just happened, which is what the next decision depends on. Dropping
    #    is done from the front and then repaired, never mid-pair.
    kept = list(rest)
    while kept and (fixed + tools_cost + estimate_tokens(kept)) > budget:
        if len(kept) <= 2:
            break
        kept.pop(0)
        dropped_history += 1

    # A tool result whose originating assistant call was trimmed is an orphan.
    # Most chat APIs reject that outright, and no model can interpret it, so
    # leading orphans are removed rather than sent.
    while kept and kept[0].get("role") == "tool":
        kept.pop(0)
        dropped_history += 1

    if dropped_history:
        notes.append(f"dropped {dropped_history} older message(s) to fit")

    total = fixed + tools_cost + estimate_tokens(kept)

    # 2. Only if history alone was not enough do we touch the tool surface —
    #    and by removing whole tools, never by truncating their schemas.
    if total > budget and tools:
        # Never strip the tool surface to nothing. A model with no tools cannot
        # act and is given no reason why — observed for real ("offering 0 of 33
        # tools") when a single oversized tool result filled the budget. Below
        # this floor the honest answer is that the request does not fit, which
        # the caller reports, rather than a silently disarmed model.
        minimum_tools = min(MINIMUM_TOOLS_OFFERED, len(tools))
        kept_tools = list(tools)
        while (
            len(kept_tools) > minimum_tools
            and (fixed + estimate_tokens(kept_tools) + estimate_tokens(kept)) > budget
        ):
            kept_tools.pop()
            dropped_tools += 1
        tools = kept_tools or None
        if dropped_tools and len(kept_tools) <= minimum_tools:
            notes.append("hit the minimum tool floor")
        tools_cost = estimate_tokens(tools) if tools else 0
        total = fixed + tools_cost + estimate_tokens(kept)
        if dropped_tools:
            # Worth a warning: Mike is now offering the model a smaller set of
            # capabilities than it actually has, which changes what it can do.
            logger.warning(
                "Context pressure: offering %d of %d tools to %s",
                len(tools or []), len(tools or []) + dropped_tools, capabilities.model,
            )
            notes.append(
                f"offered {len(tools or [])} of {len(tools or []) + dropped_tools} tools"
            )

    # 3. Still too big: refuse rather than send something that will be cut.
    if total > budget:
        return RequestPlan(
            messages=_assemble(kept),
            tools=tools,
            estimated_tokens=total,
            budget=budget,
            dropped_history=dropped_history,
            dropped_tools=dropped_tools,
            notes=notes,
            error=BrainError(
                kind="context",
                message=(
                    "This request is too large for the current model even after "
                    "trimming. Try a shorter message, or switch to a model with "
                    "a larger context."
                ),
                detail=f"estimated {total} tokens against a {budget} token budget",
            ),
        )

    return RequestPlan(
        messages=_assemble(kept),
        tools=tools,
        estimated_tokens=total,
        budget=budget,
        dropped_history=dropped_history,
        dropped_tools=dropped_tools,
        notes=notes,
    )
