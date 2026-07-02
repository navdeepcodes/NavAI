from tools.permissions.policies import (
    SAFE,
    CONFIRM,
    BLOCKED
)


class PermissionManager:

    def check(self, tool_name):

        if tool_name in BLOCKED:

            return "blocked"

        if tool_name in CONFIRM:

            return "confirm"

        return "allow"