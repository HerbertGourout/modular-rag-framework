"""Request-size and rate-limit middleware (Lot 16a, docs/refactoring-plan.md
-- "rate and request-size limits"). Both are genuine, tested, in-process
implementations, not stubs -- scoped honestly to a single-process
deployment: state is an in-memory dict per middleware instance, so it
resets on restart and is not shared across horizontally-scaled replicas.
A shared-store (Redis) backend is the production upgrade path if this API
is ever deployed with more than one worker process; recorded here rather
than silently implied by the class names.

`/health` and `/ready` are excluded from both -- an orchestrator's own
liveness/readiness probes must never be the thing that trips a rate limit
or gets rejected for a header it doesn't control.
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
