from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto

from brain.providers.base_llm_provider import BaseLLMProvider


class ProviderStatus(Enum):
    """
    Runtime state of a provider.
    """

    ACTIVE = auto()

    AVAILABLE = auto()

    COOLDOWN = auto()

    OFFLINE = auto()


@dataclass(slots=True)
class ProviderState:
    """
    Runtime information for a provider.

    One instance exists for every registered provider.
    """

    provider: BaseLLMProvider

    status: ProviderStatus = ProviderStatus.AVAILABLE

    # =========================================================
    # Runtime timestamps
    # =========================================================

    cooldown_until: datetime | None = None

    last_used: datetime | None = None

    last_success: datetime | None = None

    last_failure: datetime | None = None

    # =========================================================
    # Performance
    # =========================================================

    latency_ms: float = 0.0

    average_latency_ms: float = 0.0

    # =========================================================
    # Statistics
    # =========================================================

    total_requests: int = 0

    success_count: int = 0

    failure_count: int = 0

    consecutive_failures: int = 0

    # =========================================================

    metadata: dict[str, object] = field(
        default_factory=dict
    )

    # =========================================================
    # Properties
    # =========================================================

    @property
    def available(self) -> bool:

        return self.status in (

            ProviderStatus.ACTIVE,

            ProviderStatus.AVAILABLE,

        )

    # ---------------------------------------------------------

    @property
    def cooling_down(self) -> bool:

        return self.status == ProviderStatus.COOLDOWN

    # ---------------------------------------------------------

    @property
    def offline(self) -> bool:

        return self.status == ProviderStatus.OFFLINE

    # ---------------------------------------------------------

    @property
    def success_rate(self) -> float:

        if self.total_requests == 0:

            return 0.0

        return self.success_count / self.total_requests

    # =========================================================
    # Runtime Updates
    # =========================================================

    def mark_used(self) -> None:

        self.last_used = datetime.now()

        self.total_requests += 1

    # ---------------------------------------------------------

    def mark_success(
        self,
        latency_ms: float,
    ) -> None:

        self.mark_used()

        self.status = ProviderStatus.ACTIVE

        self.cooldown_until = None

        self.last_success = datetime.now()

        self.success_count += 1

        self.consecutive_failures = 0

        self.latency_ms = latency_ms

        if self.success_count == 1:

            self.average_latency_ms = latency_ms

        else:

            self.average_latency_ms = (

                (
                    self.average_latency_ms
                    * (self.success_count - 1)
                )
                + latency_ms

            ) / self.success_count

    # ---------------------------------------------------------

    def mark_failure(
        self,
        *,
        cooldown_seconds: int = 7200,
        failure_threshold: int = 2,
    ) -> None:

        self.mark_used()

        self.last_failure = datetime.now()

        self.failure_count += 1

        self.consecutive_failures += 1

        self.latency_ms = 0.0

        if self.consecutive_failures >= failure_threshold:

            self.start_cooldown(
                cooldown_seconds
            )

    # ---------------------------------------------------------

    def start_cooldown(
        self,
        seconds: int,
    ) -> None:

        self.status = ProviderStatus.COOLDOWN

        self.cooldown_until = (

            datetime.now()

            + timedelta(
                seconds=seconds
            )

        )

    # ---------------------------------------------------------

    def recover(self) -> None:

        self.status = ProviderStatus.ACTIVE

        self.cooldown_until = None

        self.consecutive_failures = 0

    # ---------------------------------------------------------

    def reset(self) -> None:

        self.status = ProviderStatus.AVAILABLE

        self.cooldown_until = None

        self.consecutive_failures = 0

        self.latency_ms = 0.0