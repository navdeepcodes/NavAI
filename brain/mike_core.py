from __future__ import annotations

import threading
import time
from typing import Any

from brain import situation_store
from logs.logger import logger


# Two different things used to share this one number, and the loud one won.
#
# Every agent step appends an assistant message plus one `tool` message per
# call, so a single ordinary task adds dozens of entries. Measured: after two
# twelve-step tasks a 40-message window held 20 assistant, 18 tool and *two*
# user messages — the conversation had been evicted by its own tool traffic,
# and "call the project Apollo" was gone before the user said "change its name
# to Nova". That is the reference failure, and it is structural: the working
# notes of a finished task were outranking what the user actually said.
#
# So the window is bigger (the token budget in context_budget.py is the real
# ceiling, and it has room to spare), and trimming now distinguishes the
# conversation from the tool trace instead of treating them as one stream.
MAX_HISTORY = 80
MAX_TOOL_LOG = 10
SUMMARY_TRIGGER_TURNS = 6

# The situation summary is a full call to the same local model (measured: ~73
# output tokens at ~4.5 tok/s, ~25 s). It used to run every SUMMARY_TRIGGER_TURNS
# turns, immediately — so the next thing the student said queued behind it and
# a 4 s answer took 29 s, every sixth turn, in conversations short enough that
# every turn was still in context anyway. It is only needed once history nears
# the trim point (old turns are about to be dropped), so it now runs only then,
# and only after Mike has been idle for a moment; if the user starts a new turn
# first, it backs off and is rescheduled after that turn.
SUMMARY_HEADROOM = 20          # start summarising this many messages before the trim
SUMMARY_IDLE_SECONDS = 20.0    # ...and only after this long with no new turn
VISION_FRESHNESS_SECONDS = 120

SUMMARY_PROMPT = """\
You maintain a short internal summary of an ongoing conversation between a user \
and their AI assistant, Mike.

Current summary:
{old_summary}

New messages since that summary:
{new_turns}

Rewrite the summary in 2-4 short sentences. Cover what the user is working on, \
any open or unfinished threads, and important context — not a transcript. If there's \
a goal being actively worked toward, include what's been done so far and what's left, \
in plain language.

Rules:
- Only state something as fact if the user said it directly.
- Use words like "likely" or "seems like" for anything inferred, not stated.
- If the new messages contradict the current summary, the new messages are correct \
— the user's most recent explicit statement always overrides an older inference.
- Never invent detail that wasn't said or observed.
- Keep it to a short paragraph. Do not list every message.

Return only the new summary text, nothing else.\
"""


def _segment_history(history: list[dict]) -> list[tuple[str, list[dict]]]:
    """Split history into conversation and tool exchanges, in order.

    A "tool" segment is one assistant message carrying tool calls plus the
    tool results that answer it. They are grouped because they are only
    meaningful together: a result whose call has been dropped is an orphan
    that no model can interpret and some providers reject outright.
    """
    segments: list[tuple[str, list[dict]]] = []
    index = 0
    count = len(history)

    while index < count:
        message = history[index]
        if message.get("role") == "assistant" and message.get("tool_calls"):
            group = [message]
            index += 1
            while index < count and history[index].get("role") == "tool":
                group.append(history[index])
                index += 1
            segments.append(("tool", group))
        elif message.get("role") == "tool":
            # An orphan already — keep it grouped as tool traffic so it is
            # given up before conversation is.
            segments.append(("tool", [message]))
            index += 1
        else:
            segments.append(("talk", [message]))
            index += 1

    return segments


class MikeCore:
    """
    Mike's persistent state — what's currently going on, compressed enough
    to survive a scrollback that's long gone from view.

    MikeCore does not resolve pronouns, extract entities, or rewrite the
    user's words. Qwen3 does that itself from the raw conversation window;
    this class only carries forward what's fallen out of that window.
    """

    # =====================================================
    # Construction
    # =====================================================

    def __init__(
        self,
        *,
        host: str,
        summary_model: str,
    ) -> None:

        self._host = host
        self._summary_model = summary_model

        self.history: list[dict[str, Any]] = []

        self.tool_log: list[str] = []

        # None = no project attached (the global scope). Resolved fresh each
        # message via sync_project(), not cached indefinitely — the IDE
        # workspace can change while Mike keeps running.
        self.project_id: int | None = None
        # Starts empty. The summary describes *one conversation*, and it used to
        # be loaded from a single global row here — so the summary of whatever
        # was said days ago ("the user says nothing is going right…") was
        # injected into every turn of every later session, and a student's
        # first "hey" was answered with "rough day?". A conversation's summary
        # now travels with that conversation (conversation_store) and is put
        # back only by restore_conversation().
        self.situation_summary: str = ""

        self._last_vision: tuple[str, float] | None = None

        self._turns_since_summary = 0
        self._summarizing = False

        # Bumped whenever the conversation is replaced (new chat / reopened
        # chat). A background summary refresh records the epoch it started in
        # and is discarded if the conversation changed underneath it, so a
        # summary of the old chat can never land on the new one.
        self._epoch = 0

    # =====================================================
    # Conversation lifecycle
    # =====================================================

    def reset_conversation(self) -> None:
        """Start a genuinely fresh conversation: no turns, no summary, no
        'recent activity' carried over from the one before."""
        self._epoch += 1
        self.history = []
        self.tool_log = []
        self.situation_summary = ""
        self._turns_since_summary = 0

    def restore_conversation(self, turns: list[dict[str, Any]], summary: str = "") -> None:
        """Put a saved conversation back so Mike continues it with the same
        context he had: its user/assistant turns and its own summary."""
        self.reset_conversation()
        self.history = [
            {"role": t["role"], "content": t["content"]}
            for t in turns
            if t.get("role") in ("user", "assistant") and t.get("content")
        ]
        self.situation_summary = summary or ""
        self.trim_history()

    # =====================================================
    # Project scope
    # =====================================================

    def sync_project(self) -> None:
        """
        Call once per message. If the attached IDE workspace has changed
        since last time — including going from "some project" to "none" —
        swap in that project's own situation summary instead of the global
        one, so continuity actually differs by what you're working on.
        """
        from brain import projects

        try:
            new_id = projects.current()
        except Exception:
            new_id = None

        if new_id == self.project_id:
            return

        self.project_id = new_id
        # A project keeps a summary of the work in that repo. Leaving every
        # project (back to no project) must not resurrect some unrelated old
        # global summary — see __init__.
        self.situation_summary = (
            situation_store.load(project_id=new_id) if new_id is not None else ""
        )

    # =====================================================
    # Conversation history
    # =====================================================

    def trim_history(self) -> None:
        """Make room without throwing away what the next sentence depends on.

        Dropping the oldest messages is the obvious rule and the wrong one: a
        tool-heavy task is mostly tool messages, so "oldest first" deletes the
        conversation and keeps the bookkeeping. What survives has to be chosen
        by *kind*, not by age alone.

        The order things are given up in:

          1. tool exchanges from turns that are already finished — their
             outcome is already carried by the tool log and the situation
             summary, so the step-by-step trace is the cheapest thing to lose
          2. only then, the oldest conversation

        The tool exchanges of the *current* turn are never dropped: Mike is
        still working through them, and losing them makes him repeat work he
        has already done. Groups move as a unit, so a tool result is never
        separated from the call that produced it.
        """
        if len(self.history) <= MAX_HISTORY:
            return

        segments = _segment_history(self.history)

        # The current turn starts at the last thing the user said; everything
        # after it is live working state, not history.
        live_from = 0
        for index, (kind, _group) in enumerate(segments):
            if kind == "talk" and _group[0].get("role") == "user":
                live_from = index

        total = len(self.history)
        keep: list[tuple[str, list[dict]] | None] = list(segments)

        for index, (kind, group) in enumerate(segments):
            if total <= MAX_HISTORY:
                break
            if kind == "tool" and index < live_from:
                keep[index] = None
                total -= len(group)

        surviving = [item for item in keep if item is not None]

        # Still over: the conversation itself is longer than the window, so
        # the oldest of it goes — the ordinary rule, reached last rather than
        # first.
        while total > MAX_HISTORY and surviving:
            _kind, group = surviving.pop(0)
            total -= len(group)

        self.history = [msg for _kind, group in surviving for msg in group]

    # -----------------------------------------------------

    def note_turn_complete(self) -> None:

        self._turns_since_summary += 1

        self._maybe_refresh_summary()

    # =====================================================
    # Tool activity
    # =====================================================

    def add_tool_result(
        self,
        status: str,
    ) -> None:

        self.tool_log.append(status)

        self.tool_log = self.tool_log[-MAX_TOOL_LOG:]

    # =====================================================
    # Vision
    # =====================================================

    def set_vision(
        self,
        description: str,
    ) -> None:

        self._last_vision = (description, time.monotonic())

    # -----------------------------------------------------

    def _fresh_vision(self) -> str | None:

        if self._last_vision is None:
            return None

        description, seen_at = self._last_vision

        if time.monotonic() - seen_at > VISION_FRESHNESS_SECONDS:
            return None

        return description

    # =====================================================
    # Prompt context
    # =====================================================

    def to_prompt_context(self) -> str:

        parts: list[str] = []

        if self.situation_summary:

            parts.append(
                f"Situation:\n{self.situation_summary}"
            )

        if self.tool_log:

            recent = "\n".join(
                f"- {entry}" for entry in self.tool_log[-3:]
            )

            parts.append(
                f"Recent activity:\n{recent}"
            )

        vision = self._fresh_vision()

        if vision:

            parts.append(
                f"What's currently on screen:\n{vision}"
            )

        return "\n\n".join(parts)

    # =====================================================
    # Situation summary refresh (background, non-blocking)
    # =====================================================

    def _maybe_refresh_summary(self) -> None:

        # Only when old turns are about to be trimmed away: before that point
        # the full conversation is already in context and a summary adds a
        # ~25 s model call for nothing.
        near_limit = len(self.history) >= MAX_HISTORY - SUMMARY_HEADROOM
        if not near_limit:
            return

        if self._summarizing:
            return

        self._summarizing = True
        threading.Thread(
            target=self._refresh_when_idle,
            args=(len(self.history), self._epoch),
            daemon=True,
        ).start()

    def _refresh_when_idle(self, history_len: int, epoch: int) -> None:
        """Wait for a quiet moment, then summarise — never in front of the
        user's next message. The local model serves one request at a time, so
        a summary started as a turn ends is a summary the next turn waits for."""
        # Right at the trim point there's no time to wait for a quiet moment:
        # summarise now rather than let turns be dropped unsummarised.
        urgent = history_len >= MAX_HISTORY - 4
        deadline = time.monotonic() + (0.0 if urgent else SUMMARY_IDLE_SECONDS)
        while time.monotonic() < deadline:
            if len(self.history) != history_len or epoch != self._epoch:
                # A new turn (or a different conversation) began: back off.
                # The next completed turn schedules another attempt.
                self._summarizing = False
                return
            time.sleep(0.25)

        self._turns_since_summary = 0
        self._refresh_summary(
            self.situation_summary, list(self.history), self.project_id, epoch)

    # -----------------------------------------------------

    def _refresh_summary(
        self,
        old_summary: str,
        turns: list[dict],
        project_id: int | None,
        epoch: int | None = None,
    ) -> None:

        try:

            # The per-turn context snapshots the runtime records (what app was
            # focused, what a tool just did) are notes to the model, not things
            # anyone said. Summarising them back produces a "summary" of Mike's
            # own bookkeeping instead of the conversation.
            transcript = "\n".join(
                f"{turn.get('role', '?')}: {turn.get('content', '')}"
                for turn in turns
                if turn.get("content") and turn.get("role") != "system"
            )

            prompt = SUMMARY_PROMPT.format(
                old_summary=old_summary or "(none yet)",
                new_turns=transcript or "(none)",
            )

            # Summarisation goes through the provider boundary like every
            # other model call, so the summariser can be a different brain —
            # or a different backend entirely — without changing this code.
            from brain.providers import get_provider

            result = get_provider(model=self._summary_model).complete(
                [{"role": "user", "content": prompt}]
            )
            if result.error is not None:
                logger.warning("Situation summary failed: %s", result.error.detail)
                return

            summary = (result.text or "").strip()

            # The conversation was replaced while this ran (new chat, or a
            # different chat reopened): this summary describes one that no
            # longer exists here, so it must not be applied or saved.
            if epoch is not None and epoch != self._epoch:
                return

            if summary:

                # Project summaries persist per project. The no-project scope
                # is conversation-owned (conversation_store) and is never
                # reloaded from situation_store, so don't write it there.
                if project_id is not None:
                    situation_store.save(summary, project_id=project_id)

                # Only update the live summary if the project hasn't changed
                # under us mid-refresh — otherwise this would clobber the
                # summary for whatever project the user has since switched
                # to, with a stale answer for the one they left.
                if self.project_id == project_id:
                    self.situation_summary = summary

        except Exception:

            logger.exception("Situation summary refresh failed.")

        finally:

            self._summarizing = False
