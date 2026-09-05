from __future__ import annotations

import threading
import time
from typing import Any

from brain import situation_store
from logs.logger import logger


MAX_HISTORY = 40
MAX_TOOL_LOG = 10
SUMMARY_TRIGGER_TURNS = 6
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
        self.situation_summary: str = situation_store.load(project_id=None)

        self._last_vision: tuple[str, float] | None = None

        self._turns_since_summary = 0
        self._summarizing = False

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
        self.situation_summary = situation_store.load(project_id=new_id)

    # =====================================================
    # Conversation history
    # =====================================================

    def trim_history(self) -> None:

        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

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

        near_limit = len(self.history) >= MAX_HISTORY - 4

        due = self._turns_since_summary >= SUMMARY_TRIGGER_TURNS

        if not (near_limit or due):
            return

        if self._summarizing:
            return

        turns_snapshot = list(self.history)
        old_summary = self.situation_summary
        project_snapshot = self.project_id

        self._summarizing = True
        self._turns_since_summary = 0

        thread = threading.Thread(
            target=self._refresh_summary,
            args=(old_summary, turns_snapshot, project_snapshot),
            daemon=True,
        )

        thread.start()

    # -----------------------------------------------------

    def _refresh_summary(
        self,
        old_summary: str,
        turns: list[dict],
        project_id: int | None,
    ) -> None:

        try:

            transcript = "\n".join(
                f"{turn.get('role', '?')}: {turn.get('content', '')}"
                for turn in turns
                if turn.get("content")
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

            if summary:

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
