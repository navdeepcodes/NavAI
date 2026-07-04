from __future__ import annotations

from brain.intelligence.thinking_result import ThinkingResult
from brain.response.response_depth import ResponseDepth
from brain.response.response_plan import ResponsePlan


class ResponsePlanner:

    def plan(
        self,
        thinking: ThinkingResult,
    ) -> ResponsePlan:

        plan = ResponsePlan()

        if thinking.intent == "greeting":

            plan.depth = ResponseDepth.SHORT

            return plan

        if thinking.intent == "question":

            plan.depth = ResponseDepth.NORMAL

            plan.include_examples = True

            return plan

        if thinking.intent == "explanation":

            plan.depth = ResponseDepth.DETAILED

            plan.include_examples = True

            plan.include_summary = True

            return plan

        return plan