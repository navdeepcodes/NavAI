from __future__ import annotations

import logging

from brain.cognition.cognition import Cognition
from brain.cognition.models.cognition_state import CognitionState
from brain.cognition.state import CognitiveState
from brain.cognition.state_machine import StateMachine
from brain.session.context_builder import ContextBuilder
from brain.session.session import Session

logger = logging.getLogger(__name__)


class CognitiveLoop:
    """
    Mike's cognitive loop.

    Responsibilities
    ----------------
    • Maintain the current conversation session.
    • Build conversational context.
    • Execute one cognition cycle.
    • Store assistant replies.
    • Track cognitive state.

    This class never:
    • plans execution
    • executes tools
    • generates responses
    """

    # =====================================================

    def __init__(self) -> None:

        self._state = StateMachine()

        self._session = Session()

        self._context_builder = ContextBuilder()

        self._cognition = Cognition()

    # =====================================================

    def process(
        self,
        message: str,
    ) -> CognitionState:

        self._state.transition(
            CognitiveState.UNDERSTANDING
        )

        try:

            # Store user message
            self._session.add_user(
                message
            )

            # Build context
            context = self._context_builder.build(
                session=self._session,
                user_message=message,
            )

            # Run cognition
            state = self._cognition.process(
                user_message=message,
                context=context,
            )

            return state

        finally:

            self._state.transition(
                CognitiveState.IDLE
            )

    # =====================================================

    def add_assistant_message(
        self,
        message: str,
    ) -> None:

        if message:

            self._session.add_assistant(
                message
            )

    # =====================================================

    def reset(
        self,
    ) -> None:

        self._session.reset()

        self._state.reset()

    # =====================================================

    @property
    def session(
        self,
    ) -> Session:

        return self._session

    # =====================================================

    @property
    def state(
        self,
    ) -> CognitiveState:

        return self._state.current