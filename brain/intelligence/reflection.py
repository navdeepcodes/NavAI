from __future__ import annotations

from brain.intelligence.models import Reflection
from tools.tool_result import ToolResult


class ReflectionEngine:
    """
    Evaluates the outcome of an action.

    Reflection allows Mike to determine whether:

    - execution succeeded
    - a retry is appropriate
    - another strategy should be attempted
    - the user should be informed
    """

    # ---------------------------------------------------------

    def reflect(
        self,
        result: ToolResult,
    ) -> Reflection:

        # -------------------------------
        # Success
        # -------------------------------

        if result.success:

            return Reflection(

                success=True,

                retry=False,

                reason="Execution completed successfully."

            )

        # -------------------------------
        # Browser
        # -------------------------------

        if result.tool == "browser":

            return Reflection(

                success=False,

                retry=False,

                reason="Browser operation failed."

            )

        # -------------------------------
        # Filesystem
        # -------------------------------

        if result.tool == "filesystem":

            return Reflection(

                success=False,

                retry=False,

                reason="Filesystem operation failed."

            )

        # -------------------------------
        # Terminal
        # -------------------------------

        if result.tool == "terminal":

            return Reflection(

                success=False,

                retry=False,

                reason="Terminal command failed."

            )

        # -------------------------------
        # Email
        # -------------------------------

        if result.tool == "email":

            return Reflection(

                success=False,

                retry=False,

                reason="Email operation failed."

            )

        # -------------------------------
        # Generic
        # -------------------------------

        return Reflection(

            success=False,

            retry=False,

            reason=result.error or "Unknown error."

        )