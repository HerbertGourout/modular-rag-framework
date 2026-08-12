"""PostgreSQL-backed AuditSink (Lot 10, docs/refactoring-plan.md — "Persist the
audit event store in PostgreSQL (append-only table, not mutated in place)").

`psycopg` is imported lazily per `.claude/.instructions.md` §4: this module is
importable without psycopg installed; only `_get_connection()` needs it. Not
declared in `pyproject.toml`'s `v1` extra — audit persistence is opt-in
infrastructure, not a V1 core-RAG runtime dependency. Install with
`pip install psycopg[binary]>=3.1` to use this sink.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from modular_rag.contracts.audit import AuditEvent
from modular_rag.core.errors import StorageError

if TYPE_CHECKING:
    import psycopg

# Append-only by design: `ON CONFLICT (id) DO NOTHING` in the INSERT below
# means a retried record() call can never overwrite an existing row, and no
# UPDATE/DELETE statement appears anywhere in this file. Enforcing that at
# the database-permission level (a role with INSERT/SELECT only, no
# UPDATE/DELETE grants) is a deployment concern — Lot 16c's runbooks — not
# something this adapter can guarantee purely in Python.
_DDL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id              TEXT PRIMARY KEY,
    schema_version  TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    correlation_id  TEXT NOT NULL,
    causation_id    TEXT,
    tenant_id       TEXT NOT NULL,
    actor           TEXT,
    "timestamp"     TIMESTAMPTZ NOT NULL,
    payload         JSONB NOT NULL,
    retention_days  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant ON audit_events (tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_correlation ON audit_events (correlation_id);
"""

_INSERT = """
INSERT INTO audit_events
    (id, schema_version, event_type, correlation_id, causation_id, tenant_id,
     actor, "timestamp", payload, retention_days)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING
"""


class PostgresAuditSink:
    """Durable `AuditSink` backed by a single PostgreSQL table. Requires a
    reachable PostgreSQL instance — see `tests/integration/test_postgres_audit_sink.py`
    (`@pytest.mark.integration`, same "assumes a running local service"
    convention as `adapters/vectorstores/qdrant_store.py`'s integration tests).
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: psycopg.Connection[Any] | None = None

    def _get_connection(self) -> psycopg.Connection[Any]:
        if self._conn is None:
            try:
                import psycopg
            except ImportError as exc:
                raise ImportError(
                    "psycopg is required for PostgresAuditSink. "
                    "Install it with: pip install psycopg[binary]>=3.1"
                ) from exc
            self._conn = psycopg.connect(self._dsn, autocommit=True)
            self._conn.execute(_DDL)
        return self._conn

    def record(self, event: AuditEvent) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                _INSERT,
                (
                    event.id,
                    event.schema_version,
                    event.event_type.value,
                    event.correlation_id,
                    event.causation_id,
                    event.tenant_id,
                    event.actor,
                    event.timestamp,
                    json.dumps(event.payload),
                    event.retention_days,
                ),
            )
        except Exception as exc:
            raise StorageError(f"Failed to record audit event {event.id}: {exc}") from exc

    async def arecord(self, event: AuditEvent) -> None:
        # No native async driver wired yet (would be psycopg's AsyncConnection) —
        # documented shortcut, not a hidden one, matching the precedent set by
        # NativeEngineAdapter's capability declarations in Lot 8.
        self.record(event)

    def close(self) -> None:
        """Release the underlying connection, if one was ever opened.

        `Container.close()` discovers this via `getattr(component, "close", None)` —
        without it, this sink's connection was never released by `app.close()` despite
        the container's own docstring promising a "best-effort graceful shutdown of
        registered resources" for every component that has a `close()` method (Codex
        review, MED-003). Idempotent: calling this more than once, or on a sink that
        never opened a connection, is a safe no-op.
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def name(self) -> str:
        return "postgres"
