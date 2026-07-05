from __future__ import annotations

import logging

from brain.cognition.models.cognition_state import CognitionState
from brain.response.response_formatter import ResponseFormatter
from brain.response.response_generator import ResponseGenerator
from brain.response.response_planner import ResponsePlanner

logger = logging.getLogger(__name__)


class ResponseEngine:
    """
    Produces Mike's final response.

    Pipeline

        CognitionState
              │
              ▼
      ResponsePlanner
              │
              ▼
     ResponseGenerator
              │
              ▼
     ResponseFormatter
              │
              ▼
        Final Response

    The engine is intentionally stateless.
    Every response must be generated only from the
    current CognitionState.
    """

    # =====================================================

    def __init__(self) -> None:

        self._planner = ResponsePlanner()

        self._generator = ResponseGenerator()

        self._formatter = ResponseFormatter()

    # =====================================================

    def generate(
        self,
        state: CognitionState,
    ) -> str:

        logger.info(
            "Generating final response..."
        )

        # ----------------------------------------------
        # Never reuse a previous response
        # ----------------------------------------------

        state.final_response = None

        try:

            plan = self._planner.plan(
                state,
            )

        except Exception:

            logger.exception(
                "Response planning failed."
            )

            plan = None

        try:

            text = self._generator.generate(
                state=state,
                plan=plan,
            )

        except Exception:

            logger.exception(
                "Response generation failed."
            )

            text = ""

        try:

            text = self._formatter.format(
                text or "",
            )

        except Exception:

            logger.exception(
                "Response formatting failed."
            )

            text = text or ""

        # ----------------------------------------------
        # Final safety fallback
        # ----------------------------------------------

        if not text.strip():

            logger.warning(
                "Empty response generated."
            )

            text = (
                "I'm sorry, I don't have a good answer "
                "for that yet."
            )

        state.final_response = text

        logger.info(
            "Response generation complete."
        )

        return text