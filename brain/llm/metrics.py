from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter


# =========================================================
# Metric
# =========================================================

@dataclass(slots=True)
class Metric:

    requests: int = 0

    successes: int = 0

    failures: int = 0

    total_latency_ms: float = 0.0

    prompt_tokens: int = 0

    completion_tokens: int = 0

    total_tokens: int = 0


# =========================================================
# Metrics Collector
# =========================================================

class MetricsCollector:
    """
    Collects runtime metrics for the LLM layer.

    Metrics are grouped by task.

    Examples

        planner

        analyzer

        responder

        reflection
    """

    # ---------------------------------------------------------

    def __init__(self):

        self.metrics: dict[str, Metric] = {}

    # ---------------------------------------------------------

    def record(

        self,

        task: str,

        success: bool,

        latency_ms: float,

        prompt_tokens: int = 0,

        completion_tokens: int = 0,

    ) -> None:

        metric = self.metrics.setdefault(

            task,

            Metric()

        )

        metric.requests += 1

        if success:

            metric.successes += 1

        else:

            metric.failures += 1

        metric.total_latency_ms += latency_ms

        metric.prompt_tokens += prompt_tokens

        metric.completion_tokens += completion_tokens

        metric.total_tokens += (

            prompt_tokens +

            completion_tokens

        )

    # ---------------------------------------------------------

    def average_latency(

        self,

        task: str,

    ) -> float:

        metric = self.metrics.get(task)

        if not metric:

            return 0.0

        if metric.requests == 0:

            return 0.0

        return (

            metric.total_latency_ms /

            metric.requests

        )

    # ---------------------------------------------------------

    def success_rate(

        self,

        task: str,

    ) -> float:

        metric = self.metrics.get(task)

        if not metric:

            return 0.0

        if metric.requests == 0:

            return 0.0

        return (

            metric.successes /

            metric.requests

        )

    # ---------------------------------------------------------

    def snapshot(self) -> dict:

        report = {}

        for task, metric in self.metrics.items():

            report[task] = {

                "requests": metric.requests,

                "successes": metric.successes,

                "failures": metric.failures,

                "success_rate": self.success_rate(task),

                "average_latency_ms": self.average_latency(task),

                "total_tokens": metric.total_tokens,

            }

        return report