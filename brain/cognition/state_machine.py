from __future__ import annotations

from logs.logger import logger

from brain.cognition.state import CognitiveState


class StateMachine:
    """
    Tracks Mike's current cognitive state.
    """

    def __init__(self):

        self._state = CognitiveState.IDLE

    @property
    def current(self) -> CognitiveState:

        return self._state

    def transition(
        self,
        state: CognitiveState,
    ) -> None:

        logger.info(

            f"[STATE] {self._state.value} → {state.value}"

        )

        self._state = state

    def reset(self):

        self.transition(

            CognitiveState.IDLE

        )