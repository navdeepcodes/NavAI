from __future__ import annotations

from brain.cognition.state import CognitiveState
from brain.cognition.state_machine import StateMachine
from brain.intelligence.intelligence_engine import IntelligenceEngine
from brain.intelligence.mind import Mind


class CognitiveLoop:
    """
    Executes a single cognitive cycle.

    Responsibilities
    ----------------
    • Manage Mike's cognitive state.
    • Execute one thinking pass.
    • Return the completed Mind.
    """

    # =====================================================

    def __init__(self) -> None:

        self._state = StateMachine()

        self._intelligence = IntelligenceEngine()

    # =====================================================

    def process(
        self,
        message: str,
    ) -> Mind:

        # Mike begins thinking.

        self._state.transition(
            CognitiveState.UNDERSTANDING
        )

        mind = self._intelligence.think(
            message
        )

        # Thinking has completed.

        self._state.transition(
            CognitiveState.IDLE
        )

        return mind

    # =====================================================

    @property
    def state(self) -> CognitiveState:

        return self._state.current