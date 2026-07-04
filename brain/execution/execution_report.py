from __future__ import annotations

from dataclasses import dataclass, field

from brain.execution.execution_result import ExecutionResult


@dataclass(slots=True)
class ExecutionReport:
    """
    Final report produced after executing an execution plan.
    """

    results: list[ExecutionResult] = field(
        default_factory=list
    )

    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return all(result.success for result in self.results)

    @property
    def summary(self) -> str:
        """
        Returns the first non-empty successful message.
        """

        for result in self.results:
            if result.success and result.message:
                return result.message

        return ""

    @property
    def errors(self) -> list[str]:
        """
        Collect all execution errors.
        """

        errors: list[str] = []

        for result in self.results:
            if not result.success and result.message:
                errors.append(result.message)

        return errors

    def add(
        self,
        result: ExecutionResult,
    ) -> None:

        self.results.append(result)