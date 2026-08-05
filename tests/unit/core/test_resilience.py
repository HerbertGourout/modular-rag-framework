"""Unit tests for core/resilience.py — retry_with_backoff, CircuitBreaker.
Lot 14, docs/refactoring-plan.md.
"""
from __future__ import annotations

import pytest

from modular_rag.core.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    retry_with_backoff,
)


class _Sleeps:
    """Records requested sleep durations instead of actually sleeping."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


# ---------------------------------------------------------------------------
# retry_with_backoff
# ---------------------------------------------------------------------------


def test_retry_returns_immediately_on_first_success():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = retry_with_backoff(fn, sleep=_Sleeps())

    assert result == "ok"
    assert len(calls) == 1


def test_retry_retries_on_a_retryable_error_then_succeeds():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    sleeps = _Sleeps()
    result = retry_with_backoff(fn, max_attempts=5, base_delay=0.1, sleep=sleeps)

    assert result == "ok"
    assert attempts["n"] == 3
    assert len(sleeps.calls) == 2  # slept before attempt 2 and 3


def test_retry_uses_exponential_backoff():
    def fn():
        raise ConnectionError("always fails")

    sleeps = _Sleeps()
    with pytest.raises(ConnectionError):
        retry_with_backoff(fn, max_attempts=4, base_delay=0.1, sleep=sleeps)

    assert sleeps.calls == [0.1, 0.2, 0.4]


def test_retry_caps_delay_at_max_delay():
    def fn():
        raise ConnectionError("always fails")

    sleeps = _Sleeps()
    with pytest.raises(ConnectionError):
        retry_with_backoff(fn, max_attempts=6, base_delay=1.0, max_delay=2.0, sleep=sleeps)

    assert max(sleeps.calls) <= 2.0


def test_retry_reraises_after_exhausting_attempts():
    def fn():
        raise ConnectionError("always fails")

    with pytest.raises(ConnectionError):
        retry_with_backoff(fn, max_attempts=3, sleep=_Sleeps())


def test_retry_does_not_retry_a_non_retryable_error():
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        retry_with_backoff(fn, sleep=_Sleeps())

    assert len(calls) == 1  # never retried


def test_retry_never_retries_a_security_error():
    """Retry eligibility (Lot 14): a deliberate denial must never be retried
    as if it were a transient failure."""
    from modular_rag.core.errors import SecurityError

    def fn():
        raise SecurityError("blocked")

    with pytest.raises(SecurityError):
        retry_with_backoff(fn, sleep=_Sleeps())


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_starts_closed():
    breaker = CircuitBreaker()
    assert breaker.state == CircuitState.CLOSED


def test_circuit_breaker_calls_through_when_closed():
    breaker = CircuitBreaker()
    assert breaker.call(lambda: "ok") == "ok"


def test_circuit_breaker_opens_after_threshold_failures():
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, clock=clock)

    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.call(_raise)

    assert breaker.state == CircuitState.OPEN


def test_circuit_breaker_fails_fast_while_open():
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, clock=clock)

    with pytest.raises(RuntimeError):
        breaker.call(_raise)
    assert breaker.state == CircuitState.OPEN

    with pytest.raises(CircuitBreakerOpenError):
        breaker.call(lambda: "should not be called")


def test_circuit_breaker_becomes_half_open_after_reset_timeout():
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=30.0, clock=clock)
    with pytest.raises(RuntimeError):
        breaker.call(_raise)
    assert breaker.state == CircuitState.OPEN

    clock.advance(31.0)

    assert breaker.state == CircuitState.HALF_OPEN


def test_circuit_breaker_half_open_success_closes_the_circuit():
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=30.0, clock=clock)
    with pytest.raises(RuntimeError):
        breaker.call(_raise)
    clock.advance(31.0)

    result = breaker.call(lambda: "ok")

    assert result == "ok"
    assert breaker.state == CircuitState.CLOSED


def test_circuit_breaker_half_open_failure_reopens_immediately():
    """A failed trial must re-open right away, not require re-accumulating
    failure_threshold failures from scratch."""
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30.0, clock=clock)
    for _ in range(5):
        with pytest.raises(RuntimeError):
            breaker.call(_raise)
    assert breaker.state == CircuitState.OPEN

    clock.advance(31.0)
    assert breaker.state == CircuitState.HALF_OPEN

    with pytest.raises(RuntimeError):
        breaker.call(_raise)  # the half-open trial itself fails

    assert breaker.state == CircuitState.OPEN  # reopened after just one failure


def _raise():
    raise RuntimeError("boom")
