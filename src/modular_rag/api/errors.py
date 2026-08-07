"""Typed-safe HTTP error mapping (Lot 16a, docs/refactoring-plan.md --
"typed safe errors... internal exception strings... can leak to
callers"). `create_app()`'s previous `except Exception: raise
HTTPException(status_code=500, detail=str(exc))` returned raw Python
exception text -- stack-trace fragments, file paths, connection strings --
to any caller on any failure.

Two error families are treated as genuinely caller-facing, because their
message already *is* the safe explanation a caller needs (this is the
existing convention elsewhere in the codebase: `SecurityGuard.check_query()`
returns a human-readable `reason` precisely so it can be shown to the
caller, not logged and hidden):

- `AuthenticationError` -- invalid/expired/missing token, wrong audience.
- `SecurityError` (covers `PolicyViolationError`) -- a governance/policy
  denial the caller needs to see to understand why the request failed.

Everything else -- `ConfigurationError` (may contain server-side manifest
paths), any other `ModularRAGError` (retrieval/generation/ingestion/storage
failures), or a non-framework exception -- is logged in full server-side and
replaced with a generic message plus a correlation id, never the raw
exception text.
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import HTTPException

from modular_rag.app.public import AuthenticationError, ModularRAGError, SecurityError

log = structlog.get_logger(__name__)


def to_http_exception(exc: Exception) -> HTTPException:
    """Convert any exception raised while handling a request into a
    caller-safe `HTTPException`. Always logs the original exception in full
    server-side first, under a correlation id the caller also receives."""
    correlation_id = str(uuid.uuid4())
    log.warning(
        "api.request_failed",
        correlation_id=correlation_id,
        error_type=type(exc).__name__,
        error=str(exc),
    )

    if isinstance(exc, AuthenticationError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, SecurityError):  # PolicyViolationError included
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ModularRAGError):
        return HTTPException(
            status_code=502, detail=f"Request failed (reference: {correlation_id})."
        )
    return HTTPException(
        status_code=500, detail=f"Internal server error (reference: {correlation_id})."
    )
