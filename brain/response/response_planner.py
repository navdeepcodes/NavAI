from __future__ import annotations

from brain.cognition.models.cognition_state import CognitionState
from brain.response.response_depth import ResponseDepth
from brain.response.response_plan import ResponsePlan


class ResponsePlanner:

    def plan(
        self,
        state: CognitionState,
    ) -> ResponsePlan:

        plan = ResponsePlan()

        if state.action == "CLARIFY":

            plan.depth = ResponseDepth.SHORT

            return plan

        if state.action == "PLAN":

            plan.depth = ResponseDepth.SHORT

            return plan

        if state.intent in (
            "explanation",
            "teach",
            "learn",
        ):

            plan.depth = ResponseDepth.DETAILED

            plan.include_examples = True

            plan.include_summary = True

            return plan

        plan.depth = ResponseDepth.NORMAL

        return plan