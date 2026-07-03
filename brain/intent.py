from brain.intent_prompt import INTENT_PROMPT

from brain.provider import get_provider


class IntentEngine:

    # ---------------------------------------------------------

    def __init__(self):

        pass

    # ---------------------------------------------------------

    def detect(
        self,
        request: str
    ) -> str:

        provider = get_provider()

        prompt = f"""
{INTENT_PROMPT}

User:
{request}

Intent:
"""

        result = provider.complete(prompt)

        return result.strip().upper()