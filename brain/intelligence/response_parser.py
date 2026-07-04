from __future__ import annotations

import json
from typing import Any

from brain.intelligence.mind import Mind


class ResponsePromptBuilder:
    """
    Builds the prompt for Mike's Response LLM.

    Responsibilities
    ----------------
    • Convert Mike's complete cognitive state into prompt context.
    • Never perform reasoning.
    • Never modify the Mind.
    • Never decide what Mike should say.
    • Never generate natural language.

    This class is purely responsible for serialization.
    """

    # ---------------------------------------------------------

    def build(
        self,
        mind: Mind,
    ) -> str:

        payload = {

            "user_message": mind.user_message,

            "understanding": self._understanding(
                mind,
            ),

            "reasoning": self._reasoning(
                mind,
            ),

            "decision": self._decision(
                mind,
            ),

            "context": self._context(
                mind,
            ),

            "memory": self._memory(
                mind,
            ),

            "planner": self._planner(
                mind,
            ),

            "tools": self._tools(
                mind,
            ),

            "emotion": self._emotion(
                mind,
            ),

            "confidence": self._confidence(
                mind,
            ),

        }

        return json.dumps(

            payload,

            indent=2,

            ensure_ascii=False,

            default=self._serialize,

        )

    # ---------------------------------------------------------
    # Understanding
    # ---------------------------------------------------------

    def _understanding(
        self,
        mind: Mind,
    ) -> dict[str, Any]:

        u = mind.understanding

        return {

            "goal": u.goal,

            "intent": u.intent,

            "entities": u.entities,

            "constraints": u.constraints,

            "confidence": u.confidence,

            "emotional_tone": str(
                u.emotional_tone
            ),

        }

    # ---------------------------------------------------------
    # Reasoning
    # ---------------------------------------------------------

    def _reasoning(
        self,
        mind: Mind,
    ) -> dict[str, Any]:

        r = mind.reasoning

        return {

            "thoughts": r.thoughts,

            "observations": r.observations,

            "assumptions": r.assumptions,

        }

    # ---------------------------------------------------------
    # Decision
    # ---------------------------------------------------------

    def _decision(
        self,
        mind: Mind,
    ) -> dict[str, Any]:

        d = mind.decision

        return {

            "action": d.action.name,

            "requires_planning": d.requires_planning,

            "requires_memory": d.requires_memory,

            "requires_clarification":
                d.requires_clarification,

            "clarification_question":
                d.clarification_question,

            "reasoning": getattr(
                d,
                "reasoning",
                "",
            ),

        }

    # ---------------------------------------------------------
    # Context
    # ---------------------------------------------------------

    def _context(
        self,
        mind: Mind,
    ) -> dict[str, Any]:

        c = mind.context

        return {

            "current_task":
                c.current_task,

            "conversation":
                c.previous_messages,

            "active_project":
                c.active_project,

            "working_directory":
                c.working_directory,

        }

    # ---------------------------------------------------------
    # Memory
    # ---------------------------------------------------------

    def _memory(
        self,
        mind: Mind,
    ) -> Any:

        return getattr(

            mind,

            "memory_result",

            None,

        )

    # ---------------------------------------------------------
    # Planner
    # ---------------------------------------------------------

    def _planner(
        self,
        mind: Mind,
    ) -> list[dict[str, Any]]:

        tasks = getattr(

            mind,

            "planner_tasks",

            [],

        )

        return [

            {

                "description":
                    task.description,

                "tool":
                    task.tool,

                "action":
                    task.action,

                "arguments":
                    task.arguments,

                "completed":
                    task.completed,

            }

            for task in tasks

        ]

    # ---------------------------------------------------------
    # Tool Results
    # ---------------------------------------------------------

    def _tools(
        self,
        mind: Mind,
    ) -> list[dict[str, Any]]:

        results = getattr(

            mind,

            "tool_results",

            [],

        )

        return [

            {

                "success":
                    result.success,

                "tool":
                    result.tool,

                "action":
                    result.action,

                "message":
                    result.message,

                "error":
                    result.error,

            }

            for result in results

        ]

    # ---------------------------------------------------------
    # Emotion
    # ---------------------------------------------------------

    def _emotion(
        self,
        mind: Mind,
    ) -> dict[str, Any]:

        e = mind.emotion

        return {

            "label": str(
                e.label
            ),

            "confidence":
                e.confidence,

        }

    # ---------------------------------------------------------
    # Confidence
    # ---------------------------------------------------------

    def _confidence(
        self,
        mind: Mind,
    ) -> dict[str, Any]:

        c = mind.confidence

        return {

            "score": c.score,

            "explanation": c.explanation,

        }

    # ---------------------------------------------------------
    # JSON Serializer
    # ---------------------------------------------------------

    def _serialize(
        self,
        obj: Any,
    ) -> Any:

        if hasattr(

            obj,

            "__dict__",

        ):

            return obj.__dict__

        return str(obj)