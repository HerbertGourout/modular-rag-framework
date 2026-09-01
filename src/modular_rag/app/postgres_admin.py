"""Application-layer facade over the PostgreSQL migration/retention
adapters (ADR-0011 — PostgreSQL migrations, connection pooling, and audit
retention), so `cli/` (and any future `api/` equivalent) never imports
`adapters/` directly — `scripts/check_layering.py --strict` enforces "api
and cli can only import app or their own interface package" (`CLAUDE.md`
§02), the same reason `app/bootstrap.py`/`app/default_factories.py` exist
as the composition root for ordinary manifest-driven wiring. These
functions are the equivalent composition root for the standalone
administrative operations (`mrag db ...`, `mrag audit ...`) that
deliberately bypass manifest wiring entirely (ADR-0011 §7 — a schema-owning
or retention-owning DSN is never the manifest's own application-role DSN).
"""
from __future__ import annotations


def run_migrations(dsn: str, target: str | None = None) -> list[str]:
    """`mrag db migrate`. See `adapters.postgres.migrations.MigrationRunner
    .migrate()`."""
    from modular_rag.adapters.postgres.migrations import MigrationRunner

    return MigrationRunner(dsn).migrate(target=target)


def rollback_migrations(dsn: str, steps: int = 1) -> list[str]:
    """`mrag db rollback`. See `adapters.postgres.migrations.MigrationRunner
    .rollback()`."""
    from modular_rag.adapters.postgres.migrations import MigrationRunner

    return MigrationRunner(dsn).rollback(steps=steps)


def migration_status(dsn: str) -> list[str]:
    """`mrag db status`. See `adapters.postgres.migrations.MigrationRunner
    .applied_versions()`."""
    from modular_rag.adapters.postgres.migrations import MigrationRunner

    return MigrationRunner(dsn).applied_versions()


def count_expired_audit_events(dsn: str) -> int:
    """`mrag audit count-expired`. See `adapters.audit.postgres_sink
    .PostgresAuditSink.count_expired()` — read-only, does not require
    `allow_purge`."""
    from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink

    sink = PostgresAuditSink(dsn=dsn)
    try:
        return sink.count_expired()
    finally:
        sink.close()


def purge_expired_audit_events(dsn: str) -> int:
    """`mrag audit purge`. See `adapters.audit.postgres_sink
    .PostgresAuditSink.purge_expired()` — constructs the sink with
    `allow_purge=True` (the CLI's `--dsn` is documented as the dedicated
    retention-job role, never the manifest's own application DSN;
    `docs/guides/postgres-permissions.md`)."""
    from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink

    sink = PostgresAuditSink(dsn=dsn, allow_purge=True)
    try:
        return sink.purge_expired()
    finally:
        sink.close()


def count_expired_feedback(dsn: str) -> int:
    """`mrag feedback count-expired` (ADR-0014). See
    `adapters.feedback.postgres_sink.PostgresFeedbackSink.count_expired()`."""
    from modular_rag.adapters.feedback.postgres_sink import PostgresFeedbackSink

    sink = PostgresFeedbackSink(dsn=dsn)
    try:
        return sink.count_expired()
    finally:
        sink.close()


def purge_expired_feedback(dsn: str) -> int:
    """`mrag feedback purge` (ADR-0014). Same `--dsn` convention as
    `purge_expired_audit_events()` — the dedicated retention-job role, never
    the manifest's own application DSN."""
    from modular_rag.adapters.feedback.postgres_sink import PostgresFeedbackSink

    sink = PostgresFeedbackSink(dsn=dsn, allow_purge=True)
    try:
        return sink.purge_expired()
    finally:
        sink.close()


def list_pending_review_items(dsn: str) -> list[dict[str, object]]:
    """`mrag review list-pending` (ADR-0014). Returns plain dicts, not
    `ReviewItem` objects — `cli/` must not import `contracts/` models it
    only needs to print (matches this file's existing "app/ is the
    composition root; cli/ stays thin" convention)."""
    from modular_rag.adapters.review.postgres_queue import PostgresReviewQueue

    queue = PostgresReviewQueue(dsn=dsn)
    try:
        return [item.model_dump(mode="json") for item in queue.pending]
    finally:
        queue.close()


def resolve_review_item(dsn: str, item_id: str, *, approved: bool, reviewer: str) -> None:
    """`mrag review resolve` (ADR-0014). See
    `adapters.review.postgres_queue.PostgresReviewQueue.resolve()` —
    raises `ModularRAGError` if `item_id` does not exist."""
    from modular_rag.adapters.review.postgres_queue import PostgresReviewQueue

    queue = PostgresReviewQueue(dsn=dsn)
    try:
        queue.resolve(item_id, approved=approved, reviewer=reviewer)
    finally:
        queue.close()


def count_expired_review_items(dsn: str) -> int:
    """`mrag review count-expired` (ADR-0014)."""
    from modular_rag.adapters.review.postgres_queue import PostgresReviewQueue

    queue = PostgresReviewQueue(dsn=dsn)
    try:
        return queue.count_expired()
    finally:
        queue.close()


def purge_expired_review_items(dsn: str) -> int:
    """`mrag review purge` (ADR-0014). Same `--dsn`/`allow_purge` convention
    as `purge_expired_audit_events()`."""
    from modular_rag.adapters.review.postgres_queue import PostgresReviewQueue

    queue = PostgresReviewQueue(dsn=dsn, allow_purge=True)
    try:
        return queue.purge_expired()
    finally:
        queue.close()
