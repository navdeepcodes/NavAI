from brain.provider import get_provider


class Verifier:

    def __init__(self):

        self.provider = get_provider()

    def verify(

        self,

        task,

        result

    ):

        prompt = f"""
You are verifying whether a task completed successfully.

Task:
{task.description}

Result:
{result}

Reply ONLY with one word.

SUCCESS

or

FAIL
"""

        answer = self.provider.complete(
            prompt
        )

        return "SUCCESS" in answer.upper()