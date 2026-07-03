import json

from brain.task import Task


class PlannerParser:

    def parse(
        self,
        text: str
    ):

        try:

            # Remove markdown code blocks if present
            text = text.strip()

            if text.startswith("```"):

                text = text.replace(
                    "```json",
                    ""
                )

                text = text.replace(
                    "```",
                    ""
                )

                text = text.strip()

            # Parse JSON
            data = json.loads(text)

            # Allow a single object instead of a list
            if isinstance(data, dict):

                data = [data]

            tasks = []

            for i, item in enumerate(data):

                tasks.append(

                    Task(

                        id=i + 1,

                        description=item.get(
                            "description",
                            ""
                        ),

                        tool=item.get(
                            "tool"
                        ),

                        arguments=item.get(
                            "arguments",
                            {}
                        )

                    )

                )

            return tasks

        except Exception as e:

            print(
                "[PlannerParser]",
                e
            )

            return []