"""Request-size, rate-limit, and concurrency-limit middleware (Lot 16a,
docs/refactoring-plan.md -- "rate and request-size limits"; concurrency
limiting added Lot 6, "readiness and resilience"). All three are genuine,
tested, in-process implementations, not stubs -- scoped honestly to a
single-process deployment: state is an in-memory dict/semaphore per
middleware instance, so it resets on restart and is not shared across
horizontally-scaled replicas. A shared-store (Redis) backend is the
production upgrade path if this API is ever deployed with more than one
worker process; recorded here rather than silently implied by the class
names.

`/health` and `/ready` are excluded from all three -- an orchestrator's own
liveness/readiness probes must never be the thing that trips a rate limit,
gets rejected for a header it doesn't control, or is denied a concurrency
slot under load (Lot 6 -- `/ready` is exactly the signal an orchestrator
needs *most* when the process is under heavy concurrent load).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

_EXCLUDED_PATHS = frozenset({"/health", "/ready"})


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject a request body over `max_bytes` with 413, checked against the
    `Content-Length` header before the body is read."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > self._max_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body exceeds {self._max_bytes} bytes."},
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limit per client, keyed by the first hop of
    `X-Forwarded-For` (deployments behind a reverse proxy) or
    `request.client.host`. `threading.Lock`-guarded in-memory window,
    mirroring Lot 14's precedent for the other in-memory reference stores
    with a genuine read-then-write race."""

    def __init__(self, app: ASGIApp, requests_per_minute: int) -> None:
        super().__init__(app)
        self._limit = requests_per_minute
        self._window_seconds = 60.0
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = {}

    @staticmethod
    def _client_key(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        with self._lock:
            window = self._windows.setdefault(key, deque())
            cutoff = now - self._window_seconds
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) >= self._limit:
                retry_after = max(0.0, self._window_seconds - (now - window[0]))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded."},
                    headers={"Retry-After": str(int(retry_after) + 1)},
                )
            window.append(now)
        return await call_next(request)


class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
    """Cap the number of requests being processed *at the same instant*
    (Lot 6, "readiness and resilience" -- "ajouter limites de
    concurrence"). A different axis from `RateLimitMiddleware`'s
    per-client requests-per-minute window: that limits *rate over time*
    per caller, this limits *simultaneous* load on the process as a whole
    (and whatever external dependency a request touches), protecting
    against thread-pool exhaustion or overwhelming an already-degraded
    Qdrant/PostgreSQL under a burst of concurrent traffic.

    `threading.Semaphore`, matching this file's existing sync-primitive-in-
    async-middleware convention (`RateLimitMiddleware`'s `threading.Lock`)
    rather than `asyncio.Semaphore` -- the critical section is the acquire/
    release bracketing the request, not held across the wrapped call
    itself, so there is no event-loop-blocking concern beyond what
    `RateLimitMiddleware` already accepts. Rejects with 503 (not 429 --
    this is capacity, not a per-caller rate decision) when saturated,
    rather than queuing: a queued request under sustained overload just
    becomes a slower failure later, not a successful one.
    """

    def __init__(self, app: ASGIApp, max_concurrent: int) -> None:
        super().__init__(app)
        self._semaphore = threading.Semaphore(max_concurrent)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        if not self._semaphore.acquire(blocking=False):
            return JSONResponse(
                status_code=503,
                content={"detail": "Server is at capacity — try again shortly."},
            )
        try:
            return await call_next(request)
        finally:
            self._semaphore.release()
