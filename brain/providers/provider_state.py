from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto

from brain.providers.base_llm_provider import BaseLLMProvider


class ProviderStatus(Enum):
    AVAILABLE = auto()
    ACTIVE = auto()
    COOLDOWN = auto()
    OFFLINE = auto()


@dataclass(slots=True)
class ProviderState:
    """
    Runtime state of a provider.

    Tracks health, cooldowns and runtime statistics.
    """

    provider: BaseLLMProvider

    status: ProviderStatus = ProviderStatus.AVAILABLE

    cooldown_until: datetime | None = None

    last_used: datetime | None = None
    last_success: datetime | None = None
    last_failure: datetime | None = None

    latency_ms: float = 0.0
    average_latency_ms: float = 0.0

    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0

    metadata: dict[str, object] = field(default_factory=dict)

    # =====================================================

    @property
    def available(self) -> bool:
        """
        Automatically recover if cooldown has expired.
        """

        if (
            self.status == ProviderStatus.COOLDOWN
            and self.cooldown_until is not None
            and datetime.utcnow() >= self.cooldown_until
        ):
            self.recover()

        return self.status in (
            ProviderStatus.AVAILABLE,
            ProviderStatus.ACTIVE,
        )

    # =====================================================

    @property
    def healthy(self) -> bool:
        return self.available

    # =====================================================

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0

        return self.success_count / self.total_requests

    # =====================================================

    @property
    def health_score(self) -> float:

        score = 100.0

        if self.average_latency_ms > 0:
            score -= min(self.average_latency_ms / 100.0, 30.0)

        score += self.success_rate * 20.0

        score -= self.consecutive_failures * 20.0

        return max(score, 0.0)

    # =====================================================

    def mark_used(self) -> None:

        self.last_used = datetime.utcnow()

        self.total_requests += 1

        self.status = ProviderStatus.ACTIVE

    # =====================================================

    def mark_success(
        self,
        latency_ms: float,
    ) -> None:

        self.mark_used()

        self.last_success = datetime.utcnow()

        self.success_count += 1

        self.consecutive_failures = 0

        self.cooldown_until = None

        self.latency_ms = latency_ms

        if self.average_latency_ms == 0:

            self.average_latency_ms = latency_ms

        else:

            alpha = 0.2

            self.average_latency_ms = (
                alpha * latency_ms
                + (1.0 - alpha) * self.average_latency_ms
            )

        self.status = ProviderStatus.AVAILABLE

    # =====================================================

    def mark_failure(self) -> None:

        self.mark_used()

        self.last_failure = datetime.utcnow()

        self.failure_count += 1

        self.consecutive_failures += 1

        self.latency_ms = 0.0

        # DO NOT reset to AVAILABLE here.
        # ProviderSelector decides whether to cooldown or recover.

    # =====================================================

    def start_cooldown(
        self,
        seconds: int,
    ) -> None:

        self.status = ProviderStatus.COOLDOWN

        self.cooldown_until = (
            datetime.utcnow()
            + timedelta(seconds=seconds)
        )

    # =====================================================

    def recover(self) -> None:

        self.status = ProviderStatus.AVAILABLE

        self.cooldown_until = None

        self.consecutive_failures = 0

    # =====================================================

    def mark_offline(self) -> None:

        self.status = ProviderStatus.OFFLINE

    # =====================================================

    def reset(self) -> None:

        self.status = ProviderStatus.AVAILABLE

        self.cooldown_until = None

        self.last_used = None
        self.last_success = None
        self.last_failure = None

        self.latency_ms = 0.0
        self.average_latency_ms = 0.0

        self.total_requests = 0
        self.success_count = 0
        self.failure_count = 0
        self.consecutive_failures = 0

        self.metadata.clear()