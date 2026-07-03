from brain.provider import get_provider
from brain.intent_prompt import INTENT_PROMPT


class IntentEngine:

    def __init__(self):

        self.provider = get_provider()

    def detect(
        self,
        request: str
    ):

        prompt = f"""

{INTENT_PROMPT}

User:

{request}

Intent:

"""

        result = self.provider.complete(
            prompt
        )

        return result.strip().upper()