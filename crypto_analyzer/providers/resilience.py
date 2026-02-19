"""
Resilience primitives: circuit breaker, retry with exponential backoff,
and last-known-good caching.

These wrap provider calls to handle transient failures gracefully without
letting bad data propagate to the database.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry with exponential backoff."""
    max_retries: int = 3
    base_delay_s: float = 0.5
    max_delay_s: float = 10.0
    backoff_factor: float = 1.5
    retry_on_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)


@dataclass
class CircuitBreaker:
    """
    Circuit breaker preventing repeated calls to a failing provider.

    States:
    - CLOSED: Normal operation, requests pass through.
    - OPEN: Provider is failing, requests are short-circuited.
    - HALF_OPEN: After cooldown, one probe request is allowed.

    Transitions:
    - CLOSED -> OPEN: After `failure_threshold` consecutive failures.
    - OPEN -> HALF_OPEN: After `cooldown_seconds` elapse.
    - HALF_OPEN -> CLOSED: If the probe succeeds.
    - HALF_OPEN -> OPEN: If the probe fails.
    """
    provider_name: str
    failure_threshold: int = 3
    cooldown_seconds: float = 60.0
    _failure_count: int = field(default=0, init=False, repr=False)
    _state: str = field(default="CLOSED", init=False, repr=False)
    _last_failure_time: Optional[float] = field(default=None, init=False, repr=False)
    _last_error: Optional[str] = field(default=None, init=False, repr=False)

    @property
    def state(self) -> str:
        if self._state == "OPEN" and self._last_failure_time is not None:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.cooldown_seconds:
                self._state = "HALF_OPEN"
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == "OPEN"

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "CLOSED"
        self._last_error = None

    def record_failure(self, error: str) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        self._last_error = error[:500]
        if self._failure_count >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(
                "Circuit breaker OPEN for %s after %d failures: %s",
                self.provider_name, self._failure_count, error[:200],
            )

    def reset(self) -> None:
        self._failure_count = 0
        self._state = "CLOSED"
        self._last_failure_time = None
        self._last_error = None


class LastKnownGoodCache:
    """
    Cache of last successful results per key.

    When a provider fails and fallback also fails, the system can return
    the last known good value rather than propagating garbage or crashing.
    """

    def __init__(self, max_age_seconds: float = 300.0) -> None:
        self._max_age_s = max_age_seconds
        self._store: Dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, timestamp = entry
        if (time.monotonic() - timestamp) > self._max_age_s:
            return None
        return value

    def put(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.monotonic())


def resilient_call(
    func: Callable[..., T],
    *args: Any,
    retry_config: Optional[RetryConfig] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    **kwargs: Any,
) -> T:
    """
    Execute a provider call with retry + circuit breaker protection.

    Raises the last exception if all retries are exhausted or the
    circuit breaker is open.
    """
    cfg = retry_config or RetryConfig()

    if circuit_breaker and circuit_breaker.is_open:
        raise RuntimeError(
            f"Circuit breaker OPEN for {circuit_breaker.provider_name}: "
            f"{circuit_breaker.last_error}"
        )

    last_err: Optional[Exception] = None
    for attempt in range(1, cfg.max_retries + 1):
        try:
            result = func(*args, **kwargs)
            if circuit_breaker:
                circuit_breaker.record_success()
            return result
        except Exception as exc:
            last_err = exc
            err_msg = f"{type(exc).__name__}: {exc}"
            logger.debug(
                "Attempt %d/%d failed: %s", attempt, cfg.max_retries, err_msg
            )
            if attempt < cfg.max_retries:
                delay = min(
                    cfg.base_delay_s * (cfg.backoff_factor ** (attempt - 1)),
                    cfg.max_delay_s,
                )
                time.sleep(delay)

    if circuit_breaker and last_err:
        circuit_breaker.record_failure(str(last_err))

    raise last_err  # type: ignore[misc]
