from __future__ import annotations

import json
import re
from typing import Any

from brain.cognition.models.decision import Decision


class DecisionParser:
    """
    Safely converts LLM JSON into a Decision.

    This parser never raises exceptions.
    Invalid or missing fields fall back to sensible defaults.
    """

    # =====================================================

    def parse(
        self,
        text: str,
    ) -> Decision:

        try:
            payload = json.loads(
                self._extract_json(text)
            )
        except Exception:
            payload = {}

        return Decision(

            # =================================================
            # Core
            # =================================================

            action=self._string(
                payload.get("action"),
                "RESPOND",
            ),

            confidence=self._confidence(
                payload.get("confidence"),
            ),

            reasoning=self._string(
                payload.get("reasoning"),
            ),

            # =================================================
            # Decision Flags
            # =================================================

            requires_response=not self._bool(
                payload.get("requires_execution"),
            ),

            requires_execution=self._bool(
                payload.get("requires_execution"),
            ),

            requires_memory=self._bool(
                payload.get("requires_memory"),
            ),

            requires_clarification=self._bool(
                payload.get("requires_clarification"),
            ),

            # =================================================
            # Planning
            # =================================================

            execution_goal=self._optional_string(
                payload.get("execution_goal"),
            ),

            planner_hint=self._optional_string(
                payload.get("planner_hint"),
            ),

            # =================================================
            # Memory
            # =================================================

            memory_operation=self._optional_string(
                payload.get("memory_operation"),
            ),

            # =================================================
            # Metadata
            # =================================================

            metadata=self._dict(
                payload.get("metadata"),
            ),
        )

    # =====================================================

    @staticmethod
    def _extract_json(
        text: str,
    ) -> str:

        text = text.strip()

        if text.startswith("```"):

            text = re.sub(
                r"^```(?:json)?",
                "",
                text,
                flags=re.IGNORECASE,
            )

            text = re.sub(
                r"```$",
                "",
                text,
            ).strip()

        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1:
            return "{}"

        return text[start : end + 1]

    # =====================================================

    @staticmethod
    def _string(
        value: Any,
        default: str = "",
    ) -> str:

        if value is None:
            return default

        return str(value).strip()

    # =====================================================

    @staticmethod
    def _optional_string(
        value: Any,
    ) -> str | None:

        if value is None:
            return None

        value = str(value).strip()

        return value or None

    # =====================================================

    @staticmethod
    def _bool(
        value: Any,
        default: bool = False,
    ) -> bool:

        if isinstance(value, bool):
            return value

        if isinstance(value, str):

            value = value.lower()

            if value in (
                "true",
                "yes",
                "1",
            ):
                return True

            if value in (
                "false",
                "no",
                "0",
            ):
                return False

        return default

    # =====================================================

    @staticmethod
    def _confidence(
        value: Any,
    ) -> float:

        try:
            value = float(value)
        except Exception:
            return 0.0

        return max(
            0.0,
            min(
                value,
                1.0,
            ),
        )

    # =====================================================

    @staticmethod
    def _dict(
        value: Any,
    ) -> dict[str, Any]:

        if isinstance(value, dict):
            return dict(value)

        return {}