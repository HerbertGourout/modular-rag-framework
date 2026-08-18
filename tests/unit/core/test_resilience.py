"""Unit tests for core/resilience.py — retry_with_backoff, CircuitBreaker.
Lot 14, docs/refactoring-plan.md.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

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


def test_circuit_breaker_admits_only_one_half_open_trial_under_concurrency():
    """Codex review MED-001 (Lot 6): the OPEN -> HALF_OPEN transition and
    reserving the trial slot must be one atomic operation under the lock.
    Before this fix, the state read (`self.state`, which computes the
    transition from elapsed time) happened *outside* the lock in `call()`
    itself — multiple threads arriving after `reset_timeout` all
    independently observed HALF_OPEN and all entered `fn()` concurrently,
    defeating the documented "one trial call allowed" contract. Reproduced
    with 5 threads released simultaneously via a `Barrier` right after
    `reset_timeout` has elapsed: exactly one must enter `fn()`, the other 4
    must get `CircuitBreakerOpenError` immediately without ever calling it.
    """
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=10.0, clock=clock)
    with pytest.raises(RuntimeError):
        breaker.call(_raise)
    assert breaker.state == CircuitState.OPEN
    clock.advance(10.0)  # reset_timeout elapsed -> eligible for a HALF_OPEN trial

    # Track every `_enter_or_raise()` attempt (entered *or* rejected), not
    # just the winner reaching `fn()` — the winner's `fn()` blocks on
    # `release`, but if `release` were set as soon as *a* thread got in,
    # the winner could finish and close the circuit again before the other
    # 4 threads had even attempted `_enter_or_raise()`, letting them
    # through too and making this test pass even with a broken fix.
    # Waiting for all 5 attempts first guarantees the 4 losers race the
    # winner while it is still genuinely mid-trial.
    real_enter_or_raise = breaker._enter_or_raise
    attempts_done = threading.Semaphore(0)

    def _tracking_enter_or_raise() -> bool:
        try:
            return real_enter_or_raise()
        finally:
            attempts_done.release()

    breaker._enter_or_raise = _tracking_enter_or_raise  # type: ignore[method-assign]

    barrier = threading.Barrier(5)
    release = threading.Event()
    entered_count = {"n": 0}
    count_lock = threading.Lock()
    results: list[str] = []
    results_lock = threading.Lock()

    def _trial_fn() -> str:
        with count_lock:
            entered_count["n"] += 1
        assert release.wait(timeout=5), "trial deadlocked waiting for release"
        return "ok"

    def _worker() -> None:
        barrier.wait(timeout=5)
        try:
            breaker.call(_trial_fn)
            outcome = "entered"
        except CircuitBreakerOpenError:
            outcome = "rejected"
        with results_lock:
            results.append(outcome)

    threads = [threading.Thread(target=_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for _ in range(5):
        assert attempts_done.acquire(timeout=5), "not all 5 threads attempted entry"
    release.set()
    for t in threads:
        t.join(timeout=5)

    assert entered_count["n"] == 1
    assert results.count("entered") == 1
    assert results.count("rejected") == 4


def _raise():
    raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Lot 6 (readiness and resilience): CircuitBreaker is now wired into
# adapters shared across FastAPI's threadpool-executed sync routes — a
# concurrency hazard `test_circuit_breaker_opens_after_threshold_failures`
# above doesn't exercise (single-threaded, sequential calls). This proves
# the `threading.Lock` added around `_record_failure`/`_record_success`/
# `_reopen` actually prevents a lost update under real concurrent access.
# ---------------------------------------------------------------------------


def test_circuit_breaker_serializes_bookkeeping_under_concurrent_failures():
    """`call()` invokes `_record_failure()` while holding `self._lock` (see
    `CircuitBreaker`'s own docstring) — proven directly here, rather than an
    earlier version of this test that only asserted `state == OPEN` after a
    batch of concurrent failures and hoped a lost increment would show up as
    the circuit failing to open. That assertion is not a real regression
    detector on CPython: `_failure_count += 1` under the GIL is effectively
    never preempted for a plain integer increment (verified empirically,
    test-specialist review, Lot 6 — 500 runs of the pre-lock implementation
    under 20 concurrent threads, and again with a `threading.Barrier` +
    `sys.setswitchinterval(1e-9)` to force maximal interleaving, never lost
    a single increment), so the old test passed identically whether or not
    the lock existed.

    A tracking fake substituted for `_record_failure` proves the lock
    actually serializes callers instead: without it, `max_concurrent` would
    reach the thread count instead of staying at 1.
    """
    breaker = CircuitBreaker(failure_threshold=1000)  # high enough to never actually open
    tracker = _ConcurrencyTracker()
    breaker._record_failure = tracker  # type: ignore[method-assign]

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_call_and_swallow, breaker) for _ in range(10)]
        for f in futures:
            f.result()

    assert tracker.calls == 10
    assert tracker.max_concurrent == 1


class _ConcurrencyTracker:
    """Callable that records how many overlapping invocations it ever saw
    at once — guarded by its own separate lock, distinct from whatever lock
    is under test, so the tracker itself never becomes the serializing
    mechanism it's supposed to be checking for."""

    def __init__(self) -> None:
        self._tracker_lock = threading.Lock()
        self._current = 0
        self.max_concurrent = 0
        self.calls = 0

    def __call__(self) -> None:
        with self._tracker_lock:
            self._current += 1
            self.max_concurrent = max(self.max_concurrent, self._current)
            self.calls += 1
        time.sleep(0.01)  # widen the race window, matching the Postgres-adapter tests' pattern
        with self._tracker_lock:
            self._current -= 1


def _call_and_swallow(breaker: CircuitBreaker) -> None:
    try:
        breaker.call(_raise)
    except RuntimeError:
        pass
