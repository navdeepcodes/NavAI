from logs.logger import logger

from core.tool_executor import ToolExecutor


class Executor:

    def __init__(self):

        logger.info(
            "Initializing Executor..."
        )

        self.tools = ToolExecutor()

    def execute(
        self,
        task
    ):

        if task is None:

            return None

        if task.tool is None:

            logger.info(
                f"Skipping task: {task.description}"
            )

            task.completed = True

            return None

        logger.info(
            f"Executing task: {task.description}"
        )

        try:

            result = self.tools.execute(

                task.tool,

                **task.arguments

            )

            task.completed = True

            task.result = str(result)

            return result

        except Exception as e:

            logger.exception(e)

            task.completed = False

            task.result = str(e)

            return None