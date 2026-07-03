from brain.planner import Planner
from brain.executor import Executor
from brain.verifier import Verifier


class Agent:

    def __init__(self):

        self.planner = Planner()

        self.executor = Executor()

        self.verifier = Verifier()

    def run(

        self,

        request

    ):

        tasks = self.planner.plan(
            request
        )

        results = []

        for task in tasks:

            result = self.executor.execute(
                task
            )

            ok = self.verifier.verify(

                task,

                result

            )

            results.append({

                "task": task.description,

                "success": ok,

                "result": result

            })

        return results