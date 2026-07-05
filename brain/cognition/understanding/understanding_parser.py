from __future__ import annotations

import json
import re
from typing import Any

from brain.cognition.models.understanding import Understanding


class UnderstandingParser:
    """
    Converts LLM JSON into an Understanding object.

    Never raises.
    Always returns a valid Understanding.
    """

    # =====================================================

    def parse(
        self,
        text: str,
    ) -> Understanding:

        payload: dict[str, Any] = {}

        try:

            extracted = self._extract_json(text)

            if extracted:

                obj = json.loads(extracted)

                if isinstance(obj, dict):
                    payload = obj

        except Exception:
            payload = {}

        return Understanding(

            intent=self._string(
                payload.get("intent"),
                "unknown",
            ),

            goal=self._string(
                payload.get("goal"),
            ),

            confidence=self._confidence(
                payload.get("confidence"),
            ),

            requires_context=self._bool(
                payload.get("requires_context"),
            ),

            referenced_entities=self._string_list(
                payload.get("referenced_entities"),
            ),

            referenced_messages=self._string_list(
                payload.get("referenced_messages"),
            ),

            is_complete=self._bool(
                payload.get("is_complete"),
                True,
            ),

            missing_information=self._string_list(
                payload.get("missing_information"),
            ),

            clarification=self._optional_string(
                payload.get("clarification"),
            ),

            requires_memory=self._bool(
                payload.get("requires_memory"),
            ),

            memory_query=self._optional_string(
                payload.get("memory_query"),
            ),

            emotion=self._string(
                payload.get("emotion"),
                "neutral",
            ),

            tone=self._string(
                payload.get("tone"),
                "neutral",
            ),

            metadata=self._dict(
                payload.get("metadata"),
            ),
        )

    # =====================================================

    @staticmethod
    def _extract_json(
        text: str,
    ) -> str:

        if not text:
            return "{}"

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

        if start == -1 or end == -1 or end < start:
            return "{}"

        return text[start:end + 1]

    # =====================================================

    @staticmethod
    def _string(
        value: Any,
        default: str = "",
    ) -> str:

        if value is None:
            return default

        value = str(value).strip()

        return value or default

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

            value = value.strip().lower()

            if value in ("true", "yes", "1"):
                return True

            if value in ("false", "no", "0"):
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

        return max(0.0, min(1.0, value))

    # =====================================================

    @staticmethod
    def _string_list(
        value: Any,
    ) -> list[str]:

        if not isinstance(value, list):
            return []

        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    # =====================================================

    @staticmethod
    def _dict(
        value: Any,
    ) -> dict:

        if isinstance(value, dict):
            return value

        return {}