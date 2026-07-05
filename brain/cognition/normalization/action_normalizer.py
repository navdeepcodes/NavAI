from __future__ import annotations

from brain.cognition.models.decision import Decision


class ActionNormalizer:
    """
    Converts LLM-produced tool actions into Mike's canonical actions.

    Responsibilities
    ----------------
    • Normalize tool names.
    • Normalize tool actions.
    • Never call an LLM.
    • Never execute tools.
    • Never modify user intent.

    Input:
        Decision

    Output:
        Decision (normalized)
    """

    # -----------------------------------------------------

    _BROWSER_ACTIONS = {
        "open_browser": "open_browser",
        "launch_browser": "open_browser",
        "launch": "open_browser",
        "start_browser": "open_browser",

        "open_url": "open_url",
        "open_site": "open_url",
        "visit": "open_url",
        "browse_url": "open_url",

        "search": "search",
        "search_browser": "search",
        "search_web": "search",
        "search_website": "search",
        "search_on_website": "search",
        "youtube_search": "search",
        "search_youtube": "search",
        "google_search": "search",
        "web_search": "search",
        "browse": "search",
    }

    # -----------------------------------------------------

    def normalize(
        self,
        decision: Decision,
    ) -> Decision:

        if not decision.requires_execution:
            return decision

        if not decision.tool:
            return decision

        tool = decision.tool.lower()

        if tool == "browser":

            action = (
                decision.tool_action or ""
            ).lower()

            decision.tool_action = self._BROWSER_ACTIONS.get(
                action,
                action,
            )

        return decision