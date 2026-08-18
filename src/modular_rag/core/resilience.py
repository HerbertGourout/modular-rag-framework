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

import threading
import time
from collections.abc import Callable
from enum import StrEnum
from typing import TypeVar

import structlog

from modular_rag.core.errors import ModularRAGError
from modular_rag.core.ids import short_id
from modular_rag.core.models.health import DependencyHealth

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


class CircuitBreakerOpenError(ModularRAGError):
    """Raised by `CircuitBreaker.call()` when the circuit is `OPEN` — the
    wrapped call is never attempted.

    Subclasses `ModularRAGError` (Lot 6 — readiness and resilience) so
    `api/errors.py::to_http_exception()` maps it to the existing 502 "a
    framework-level dependency failure occurred" bucket automatically,
    instead of falling through to a generic, less-actionable 500 — no
    special-casing needed there.
    """


class CircuitBreaker:
    """Stop calling a failing dependency after `failure_threshold`
    consecutive failures, failing fast for `reset_timeout` seconds before
    allowing one trial call (`HALF_OPEN`). A failed trial re-opens
    immediately (does not require re-accumulating `failure_threshold`
    failures); a successful trial closes the circuit and resets the failure
    count.

    `clock` is injectable (defaults to `time.monotonic`) so tests can
    advance time deterministically instead of sleeping for `reset_timeout`.

    Lot 6 (readiness and resilience): guarded by a `threading.Lock` — this
    class was written (Lot 14) and tested single-threaded, but wiring it
    into an adapter shared across FastAPI's threadpool-executed sync routes
    (`/answer`, `/retrieve`, and now `/ready`'s own health probes) means
    `_record_failure`/`_record_success`/`_reopen`'s read-modify-write on
    `_failure_count`/`_state`/`_opened_at` is a genuine race between
    concurrent `call()` invocations — the same class of hazard already
    fixed for `BM25Retriever`/`RateLimitMiddleware` (Lot 14) and the
    Postgres adapters (Lot 6). The lock guards only the bookkeeping, never
    the wrapped `fn()` call itself — holding it across an arbitrary-duration
    external call would serialize every concurrent caller through one
    breaker instance, defeating the point of allowing concurrent attempts
    while CLOSED.
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
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        # Codex review MED-001 (Lot 6): whether a HALF_OPEN trial call is
        # currently in flight — see `_enter_or_raise()`.
        self._half_open_trial_active = False

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
        with self._lock:
            was_half_open = self._enter_or_raise()
        try:
            result = fn()
        except Exception:
            with self._lock:
                if was_half_open:
                    self._reopen()
                else:
                    self._record_failure()
            raise
        else:
            with self._lock:
                self._record_success()
            return result

    def _enter_or_raise(self) -> bool:
        """Caller must hold `self._lock`. Decide whether this call may
        proceed, and — for the OPEN -> HALF_OPEN transition and reserving
        the exclusive trial slot — do it as one atomic operation under the
        lock (Codex review MED-001, Lot 6). Previously the state read
        (`self.state`, which computes the OPEN -> HALF_OPEN transition from
        elapsed time) happened *outside* the lock, in `call()` itself:
        multiple threads arriving after `reset_timeout` all independently
        observed HALF_OPEN and all entered `fn()` concurrently, defeating
        the documented "one trial call allowed" contract — reproduced with
        five synchronized callers all entering simultaneously. Returns
        whether this call is the (exclusive) half-open trial."""
        if self._state == CircuitState.OPEN:
            if (
                self._opened_at is not None
                and self._clock() - self._opened_at >= self._reset_timeout
            ):
                self._state = CircuitState.HALF_OPEN
                self._half_open_trial_active = True
                return True
            raise CircuitBreakerOpenError(
                f"Circuit open — failing fast (retry after {self._reset_timeout}s)."
            )
        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_trial_active:
                raise CircuitBreakerOpenError(
                    "Circuit half-open — a trial call is already in progress."
                )
            self._half_open_trial_active = True
            return True
        return False

    def _reopen(self) -> None:
        """Caller must hold `self._lock`."""
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._half_open_trial_active = False
        log.warning("circuit_breaker.reopened_after_half_open_trial_failed")

    def _record_failure(self) -> None:
        """Caller must hold `self._lock`."""
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            log.warning("circuit_breaker.opened", failures=self._failure_count)

    def _record_success(self) -> None:
        """Caller must hold `self._lock`."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None
        self._half_open_trial_active = False


def unhealthy_dependency(name: str, exc: Exception, latency_ms: float = 0.0) -> DependencyHealth:
    """Build a `DependencyHealth` for a failed `check_health()` probe
    without leaking the raw exception message onto the response (Codex
    review MED-002, Lot 6).

    `GET /ready` is deliberately excluded from authentication, rate
    limiting, and the concurrency limit — an orchestrator's own readiness
    probe must never be blocked by any of them — which also means it is
    reachable by anyone who can route to the process at all. Every
    `check_health()` implementation previously put `str(exc)` directly into
    `detail`, and `/ready` serialized that field verbatim
    (`d.model_dump()`): a Qdrant/PostgreSQL exception message can embed
    hostnames, database/collection names, or content from a third-party
    SDK's own error message. This collapses that to one of a small set of
    stable, non-sensitive codes and logs the full exception server-side
    (structlog, not the response) keyed by a short correlation id that is
    also included in the public `detail` — an operator can join the two;
    an anonymous caller gets nothing more than "timeout" or "unreachable"."""
    correlation_id = short_id()
    log.warning(
        "dependency_check_failed",
        dependency=name,
        correlation_id=correlation_id,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    text = str(exc).lower()
    code = "timeout" if "timeout" in text or "timed out" in text else "unreachable"
    return DependencyHealth(
        name=name, healthy=False, detail=f"{code} ({correlation_id})", latency_ms=latency_ms
    )
