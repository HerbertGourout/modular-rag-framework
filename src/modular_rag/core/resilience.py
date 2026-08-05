"""Reliability primitives (Lot 14, docs/refactoring-plan.md — "Define
sync/async execution, timeouts, retry eligibility, cancellation, circuit
breaking, backpressure, overload, and graceful shutdown.").

Deliberately minimal and framework-agnostic: this package's actual network
calls live behind lazy-imported SDK clients (openai, anthropic,
qdrant-client) that have their own internal retry handling in some cases.
`retry_with_backoff`/`CircuitBreaker` exist for call sites this framework
owns directly, and for callers who want explicit, observable, testable
control over retry/circuit-breaking behavior rather than relying on an
SDK's own defaults. Neither is wired into any adapter automatically — that
would be a per-adapter policy decision (how many retries is right for an
LLM call vs. a vector-store call may differ), left to the caller.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from typing import TypeVar

import structlog

log = structlog.get_logger(__name__)

T = TypeVar("T")

# Retry eligibility (Lot 14: "retry eligibility"): transient/network-shaped
# failures only. Never includes programming errors (ValueError/TypeError) or
# this framework's own SecurityError/PolicyViolationError/ConfigurationError
# — retrying a deliberate denial would be actively wrong, not just wasteful.
DEFAULT_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (ConnectionError, TimeoutError)


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 10.0,
    retryable: tuple[type[Exception], ...] = DEFAULT_RETRYABLE_ERRORS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call `fn()`, retrying up to `max_attempts` times on a `retryable`
    exception with exponential backoff (`base_delay * 2**attempt`, capped at
    `max_delay`). Re-raises the last exception once attempts are exhausted.
    `sleep` is injectable so tests never actually sleep."""
    attempt = 0
    while True:
        try:
            return fn()
        except retryable as exc:
            attempt += 1
            if attempt >= max_attempts:
                log.warning("retry.exhausted", attempts=attempt, error=str(exc))
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            log.debug("retry.attempt", attempt=attempt, delay=delay, error=str(exc))
            sleep(delay)


class CircuitState(StrEnum):
    CLOSED = "closed"  # normal operation
    OPEN = "open"  # failing fast, not calling through
    HALF_OPEN = "half_open"  # one trial call allowed, to decide whether to close again


class CircuitBreakerOpenError(Exception):
    """Raised by `CircuitBreaker.call()` when the circuit is `OPEN` — the
    wrapped call is never attempted."""


class CircuitBreaker:
    """Stop calling a failing dependency after `failure_threshold`
    consecutive failures, failing fast for `reset_timeout` seconds before
    allowing one trial call (`HALF_OPEN`). A failed trial re-opens
    immediately (does not require re-accumulating `failure_threshold`
    failures); a successful trial closes the circuit and resets the failure
    count.

    `clock` is injectable (defaults to `time.monotonic`) so tests can
    advance time deterministically instead of sleeping for `reset_timeout`.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        """`OPEN` becomes `HALF_OPEN` once `reset_timeout` has elapsed —
        computed on read, not on a timer, so this stays correct without any
        background task."""
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if self._clock() - self._opened_at >= self._reset_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    def call(self, fn: Callable[[], T]) -> T:
        current = self.state
        if current == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                f"Circuit open — failing fast (retry after {self._reset_timeout}s)."
            )
        was_half_open = current == CircuitState.HALF_OPEN
        try:
            result = fn()
        except Exception:
            if was_half_open:
                self._reopen()
            else:
                self._record_failure()
            raise
        else:
            self._record_success()
            return result

    def _reopen(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        log.warning("circuit_breaker.reopened_after_half_open_trial_failed")

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            log.warning("circuit_breaker.opened", failures=self._failure_count)

    def _record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None
