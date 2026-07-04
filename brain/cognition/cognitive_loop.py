from __future__ import annotations

from brain.cognition.state import CognitiveState
from brain.cognition.state_machine import StateMachine
from brain.intelligence.intelligence_engine import IntelligenceEngine


class CognitiveLoop:

    def __init__(self):

        self.state = StateMachine()

        self.intelligence = IntelligenceEngine()

    def process(
        self,
        message: str,
    ):

        self.state.transition(
            CognitiveState.UNDERSTANDING
        )

        mind = self.intelligence.think(
            message
        )

        self.state.transition(
            CognitiveState.DECIDING
        )

        self.state.transition(
            CognitiveState.IDLE
        )

        return mind