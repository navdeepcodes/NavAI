from logs.logger import logger

from tools.tool_permission import Permission

from tools.permissions.policies import (
    SAFE,
    CONFIRM,
    BLOCKED,
)


class PermissionManager:
    """
    Central permission engine for all tool executions.

    The permission manager decides whether a tool/action pair is
    allowed immediately, requires user confirmation, or is blocked.
    """

    # ---------------------------------------------------------

    def check(
        self,
        tool: str,
        action: str | None = None,
    ) -> Permission:

        key = tool if action is None else f"{tool}.{action}"

        if (
            key in BLOCKED
            or tool in BLOCKED
        ):

            logger.warning(
                f"Permission BLOCKED: {key}"
            )

            return Permission.BLOCKED

        if (
            key in CONFIRM
            or tool in CONFIRM
        ):

            logger.info(
                f"Permission CONFIRM: {key}"
            )

            return Permission.CONFIRM

        logger.info(
            f"Permission ALLOW: {key}"
        )

        return Permission.ALLOW

    # ---------------------------------------------------------

    def is_allowed(
        self,
        tool: str,
        action: str | None = None,
    ) -> bool:

        return (
            self.check(tool, action)
            == Permission.ALLOW
        )

    # ---------------------------------------------------------

    def requires_confirmation(
        self,
        tool: str,
        action: str | None = None,
    ) -> bool:

        return (
            self.check(tool, action)
            == Permission.CONFIRM
        )

    # ---------------------------------------------------------

    def is_blocked(
        self,
        tool: str,
        action: str | None = None,
    ) -> bool:

        return (
            self.check(tool, action)
            == Permission.BLOCKED
        )