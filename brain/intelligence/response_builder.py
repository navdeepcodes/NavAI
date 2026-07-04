from __future__ import annotations

import json

from brain.intelligence.mind import Mind


class ResponsePromptBuilder:
    """
    Builds the complete cognitive context for Mike's
    Response LLM.

    Responsibilities
    ----------------
    • Serialize Mike's cognitive state.
    • Never perform reasoning.
    • Never modify the Mind.
    • Never make decisions.
    """

    # -----------------------------------------------------

    def build(
        self,
        mind: Mind,
    ) -> str:

        payload = {

            "user_message": mind.user_message,

            "understanding": {

                "goal": getattr(
                    mind.understanding,
                    "goal",
                    None,
                ),

                "intent": getattr(
                    mind.understanding,
                    "intent",
                    None,
                ),

                "entities": getattr(
                    mind.understanding,
                    "entities",
                    {},
                ),

                "confidence": getattr(
                    mind.understanding,
                    "confidence",
                    1.0,
                ),

            },

            "reasoning": {

                "thoughts": getattr(
                    mind.reasoning,
                    "thoughts",
                    [],
                ),

                "observations": getattr(
                    mind.reasoning,
                    "observations",
                    [],
                ),

                "assumptions": getattr(
                    mind.reasoning,
                    "assumptions",
                    [],
                ),

            },

            "decision": {

                "action": getattr(
                    mind.decision.action,
                    "name",
                    str(mind.decision.action),
                ),

                "clarification": getattr(
                    mind.decision,
                    "clarification_question",
                    None,
                ),

            },

            "context": {

                "messages": getattr(
                    mind.context,
                    "previous_messages",
                    [],
                )[-10:],

                "project": getattr(
                    mind.context,
                    "active_project",
                    None,
                ),

                "cwd": getattr(
                    mind.context,
                    "working_directory",
                    None,
                ),

            },

            "memory": getattr(
                mind,
                "memory_result",
                None,
            ),

            "planner_tasks": [

                getattr(task, "description", "")

                for task in getattr(
                    mind,
                    "planner_tasks",
                    [],
                )

            ],

            "tool_results": [

                {

                    "tool": getattr(
                        result,
                        "tool",
                        "",
                    ),

                    "action": getattr(
                        result,
                        "action",
                        "",
                    ),

                    "success": getattr(
                        result,
                        "success",
                        False,
                    ),

                    "message": getattr(
                        result,
                        "message",
                        "",
                    ),

                    "error": getattr(
                        result,
                        "error",
                        "",
                    ),

                }

                for result in getattr(
                    mind,
                    "tool_results",
                    [],
                )

            ],

            "emotion": {

                "label": getattr(
                    mind.emotion,
                    "label",
                    None,
                ),

                "confidence": getattr(
                    mind.emotion,
                    "confidence",
                    1.0,
                ),

            },

            "confidence": getattr(
                mind.confidence,
                "score",
                1.0,
            ),

        }

        return json.dumps(
            payload,
            indent=2,
            default=str,
        )