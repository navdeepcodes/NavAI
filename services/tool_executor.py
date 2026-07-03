from logs.logger import logger

from tools.registry import FUNCTION_MAP

from tools.permissions.permission_manager import (
    PermissionManager
)


class ToolExecutor:

    def __init__(self):

        logger.info("Initializing Tool Executor...")

        self.permission = PermissionManager()

    def execute(
        self,
        function_name: str,
        **kwargs
    ):

        logger.info(
            f"Tool Request: {function_name}"
        )

        status = self.permission.check(
            function_name
        )

        if status == "blocked":

            logger.warning(
                f"{function_name} is blocked."
            )

            return {
                "success": False,
                "message": "This action is blocked."
            }

        if status == "confirm":

            return {
                "success": False,
                "message": "Permission required."
            }

        if function_name not in FUNCTION_MAP:

            logger.error(
                f"{function_name} not found."
            )

            return {
                "success": False,
                "message": f"Unknown tool '{function_name}'."
            }

        try:

            result = FUNCTION_MAP[
                function_name
            ](**kwargs)

            return {
                "success": True,
                "result": result
            }

        except Exception as e:

            logger.exception(e)

            return {
                "success": False,
                "message": str(e)
            }