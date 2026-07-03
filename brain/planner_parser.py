import json

from logs.logger import logger

from brain.task import Task


class PlannerParser:

    # ---------------------------------------------------------

    def parse(

        self,

        text: str

    ) -> list[Task]:

        try:

            text = self._clean(

                text

            )

            data = json.loads(

                text

            )

            if isinstance(

                data,

                dict

            ):

                data = [data]

            tasks = []

            for index, item in enumerate(

                data,

                start=1

            ):

                tasks.append(

                    Task(

                        id=index,

                        description=item.get(

                            "description",

                            ""

                        ),

                        tool=item.get(

                            "tool"

                        ),

                        action=item.get(

                            "action"

                        ),

                        arguments=item.get(

                            "arguments",

                            {}

                        )

                    )

                )

            logger.info(

                f"Planner produced {len(tasks)} task(s)."

            )

            return tasks

        except Exception as e:

            logger.exception(e)

            return []

    # ---------------------------------------------------------

    def _clean(

        self,

        text: str

    ) -> str:

        text = text.strip()

        if text.startswith("```"):

            lines = text.splitlines()

            if lines:

                lines = lines[1:]

            if lines and lines[-1].strip() == "```":

                lines = lines[:-1]

            text = "\n".join(lines)

        return text.strip()