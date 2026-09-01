from __future__ import annotations

from pathlib import Path

import typer

from modular_rag.app.public import (
    ConfigurationError,
    ModularRAGError,
    PipelineManifest,
    SecurityError,
    count_expired_audit_events,
    count_expired_feedback,
    count_expired_review_items,
    create_default_registry,
    ingest_directory,
    ingest_path,
    list_pending_review_items,
    migration_status,
    purge_expired_audit_events,
    purge_expired_feedback,
    purge_expired_review_items,
    resolve_manifest,
    resolve_review_item,
    rollback_migrations,
    run_migrations,
    validate_capabilities,
)
from modular_rag.app.public import load_application as load_pipeline

app = typer.Typer(name="mrag", help="Modular RAG Framework CLI")
# ADR-0011 (PostgreSQL migrations, connection pooling, and audit retention):
# first Typer sub-apps in this CLI. `db` (migrate/rollback/status) and
# `audit` (purge/count-expired) both take an explicit `--dsn`, never
# `--manifest` — a deliberate structural choice (see each command's own
# docstring), not an oversight: `db` needs a schema-owning (`CREATE`-capable)
# role and `audit purge` needs a DELETE-capable one, neither of which the
# manifest's own `audit_sink:`/`lifecycle_ledger:` block should ever grant
# the application's normal runtime role (docs/guides/postgres-permissions.md).
db_app = typer.Typer(name="db", help="PostgreSQL schema migration commands (ADR-0011)")
audit_app = typer.Typer(name="audit", help="PostgreSQL audit-retention commands (ADR-0011)")
# ADR-0014 (Batch 14): same `--dsn`-only, never `--manifest` structural
# choice as `audit`/`db` above — feedback retention and review resolution
# both need roles the application's own runtime DSN should never hold
# (docs/guides/postgres-permissions.md).
feedback_app = typer.Typer(name="feedback", help="PostgreSQL feedback-retention commands (ADR-0014)")
review_app = typer.Typer(name="review", help="PostgreSQL human-review commands (ADR-0014)")
app.add_typer(db_app, name="db")
app.add_typer(audit_app, name="audit")
app.add_typer(feedback_app, name="feedback")
app.add_typer(review_app, name="review")

# Typed exit codes (Lot 16a, docs/refactoring-plan.md — "CLI exit codes").
# Previously every failure mode (a typo'd manifest path, a security-guard
# denial, an ingestion/retrieval crash, a genuine bug) surfaced identically
# as an uncaught Python traceback with exit code 1 — a caller scripting
# against this CLI (CI, a shell pipeline) could not distinguish "your input
# was invalid" from "the framework broke" without parsing stderr text.
EXIT_CONFIGURATION_ERROR = 2
EXIT_SECURITY_DENIAL = 3
EXIT_OPERATION_ERROR = 4


def _exit_code_for(exc: Exception) -> int:
    if isinstance(exc, ConfigurationError):
        return EXIT_CONFIGURATION_ERROR
    if isinstance(exc, SecurityError):
        return EXIT_SECURITY_DENIAL
    if isinstance(exc, ModularRAGError):
        return EXIT_OPERATION_ERROR
    return 1


def _close_application(application: object | None) -> None:
    close = getattr(application, "close", None)
    if close is not None:
        close()


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="File or directory to ingest"),  # noqa: B008
    manifest: Path = typer.Option(..., "--manifest", "-m", help="Pipeline manifest YAML"),  # noqa: B008
    tenant_id: str | None = typer.Option(
        None, "--tenant-id", help="Tenant identity for a tenant_policy-enabled manifest"
    ),
) -> None:
    """Parse, chunk, embed and index documents from a file or directory.

    `--tenant-id` (tenant-aware ingestion, follow-up to the tenant
    fail-closed fix on `ask`): applied to every parsed document before
    chunking, so every resulting chunk carries it. Omit it for a
    local/unsecured manifest with no `tenant_policy` configured — ingestion
    behaves exactly as before. Against a manifest that *does* wire a
    `tenant_policy`, `pipeline.requires_identity` is true and `--tenant-id`
    is required — checked explicitly below, not only via
    `Container.tenant_policy.enforce_ingest()`'s per-chunk loop downstream,
    which is a no-op on an empty batch (an empty directory or a
    directory containing only unsupported file types would otherwise
    "succeed" with 0 chunks indexed and no tenant ever checked).
    """
    pipeline = None
    try:
        pipeline = load_pipeline(manifest)
        if pipeline.requires_identity and not tenant_id:
            raise SecurityError(
                "This manifest requires a tenant identity (a tenant_policy is "
                "configured) — pass --tenant-id. Denied before parsing/indexing "
                "any content, including an empty or all-unsupported-files input."
            )
        if path.is_dir():
            chunks = ingest_directory(path, pipeline.chunker, tenant_id=tenant_id)
        else:
            chunks = ingest_path(path, pipeline.chunker, tenant_id=tenant_id)
        n = pipeline.ingest_chunks(chunks)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    finally:
        _close_application(pipeline)
    typer.echo(f"Indexed {n} chunks from {path}.")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to answer"),
    manifest: Path = typer.Option(..., "--manifest", "-m", help="Pipeline manifest YAML"),  # noqa: B008
    tenant_id: str | None = typer.Option(
        None, "--tenant-id", help="Tenant identity for a tenant_policy-enabled manifest"
    ),
) -> None:
    """Answer a question using the configured RAG pipeline."""
    pipeline = None
    try:
        pipeline = load_pipeline(manifest)
        answer = pipeline.answer(question, tenant_id=tenant_id)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    finally:
        _close_application(pipeline)
    typer.echo(f"\n{answer.text}\n")
    for i, citation in enumerate(answer.citations, 1):
        typer.echo(f"  [{i}] {citation.source} (score={citation.score:.3f})")


@app.command()
def validate(
    manifest: Path = typer.Argument(..., help="Pipeline manifest YAML to validate"),  # noqa: B008
) -> None:
    """Validate a manifest: schema + capability checks, no wiring/instantiation.

    Added in Lot 9 (docs/refactoring-plan.md) — catches a typo'd or
    unregistered component type, unresolved `${VAR}`/`secret://` reference,
    or unknown field, before a full pipeline load fails deep in wiring.
    """
    try:
        # ConfigurationError is the base of ManifestError and covers
        # interpolate()'s unresolved ${VAR}/secret:// failures too — both
        # are "this manifest, as given, is invalid," not distinct cases.
        pipeline_manifest = resolve_manifest(manifest)
    except ConfigurationError as exc:
        typer.echo(f"INVALID: {exc}")
        raise typer.Exit(code=1) from exc

    errors = validate_capabilities(pipeline_manifest, create_default_registry())
    if errors:
        typer.echo(f"INVALID: {manifest} — capability errors:")
        for err in errors:
            typer.echo(f"  - {err}")
        raise typer.Exit(code=1)

    typer.echo(
        f"OK: {manifest} is valid "
        f"(schema version {pipeline_manifest.version}, id={pipeline_manifest.id})"
    )


@app.command(name="manifest-schema")
def manifest_schema() -> None:
    """Print the PipelineManifest JSON Schema (for IDE tooling / diffing
    against manifests/schema/pipeline-manifest.schema.json)."""
    import json

    typer.echo(json.dumps(PipelineManifest.model_json_schema(), indent=2))


@app.command()
def version() -> None:
    """Print the framework version."""
    from modular_rag import __version__
    typer.echo(f"modular-rag {__version__}")


@app.command()
def reconcile(
    manifest: Path = typer.Option(..., "--manifest", "-m", help="Pipeline manifest YAML"),  # noqa: B008
    mode: str = typer.Option(
        "check", "--mode", help='"check" (report only) or "repair" (also delete orphaned ids)'
    ),
) -> None:
    """Detect (and optionally repair) divergence between the lifecycle
    ledger and the vector/lexical stores (ADR-0011, wrapping
    `orchestration.reconciliation.IndexReconciler`). Uses `--manifest`, not
    `--dsn`, unlike `db`/`audit` below — reconciliation reads and writes
    through the already-wired `Indexer`/`Retriever`/`lifecycle_ledger`
    components exactly as real traffic does, not a direct database
    connection, so there is no separate-credential concern to structurally
    prevent here."""
    if mode not in ("check", "repair"):
        typer.echo(f"ERROR: --mode must be 'check' or 'repair', got {mode!r}", err=True)
        raise typer.Exit(code=EXIT_CONFIGURATION_ERROR)
    pipeline = None
    try:
        pipeline = load_pipeline(manifest)
        report = pipeline.check_index_reconciliation()
        typer.echo(
            f"Checked {report.documents_checked} active documents at "
            f"{report.checked_at.isoformat()}."
        )
        if report.is_clean:
            typer.echo("No divergence found.")
        else:
            for divergence in report.divergences:
                typer.echo(
                    f"  document {divergence.document_key!r}: "
                    f"missing_in_vector={divergence.missing_in_vector}, "
                    f"missing_in_lexical={divergence.missing_in_lexical}"
                )
            if report.orphaned_in_vector:
                typer.echo(f"  orphaned_in_vector: {report.orphaned_in_vector}")
            if report.orphaned_in_lexical:
                typer.echo(f"  orphaned_in_lexical: {report.orphaned_in_lexical}")
        if mode == "repair":
            result = pipeline.repair_index_reconciliation(report)
            typer.echo(
                f"Repaired: removed {len(result.removed_orphans_in_vector)} orphaned vector id(s), "
                f"{len(result.removed_orphans_in_lexical)} orphaned lexical id(s). "
                f"{len(result.unresolved_missing)} document(s) still have missing chunks "
                "(use `mrag ingest`/rebuild-from-source to resolve — orphan cleanup cannot "
                "regenerate content that was never captured here)."
            )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    finally:
        _close_application(pipeline)


@db_app.command(name="migrate")
def db_migrate(
    dsn: str = typer.Option(
        ..., "--dsn", help="PostgreSQL DSN (migration-owning role, not the app's runtime DSN)"
    ),
    target: str | None = typer.Option(
        None,
        "--target",
        help="Migrate up to and including this version only (default: all pending)",
    ),
) -> None:
    """Apply pending schema migrations (ADR-0011). Requires a role with
    schema `CREATE` privilege — see docs/guides/postgres-permissions.md's
    `migration_role`. Deliberately `--dsn`, not `--manifest`: the
    application's own runtime role should never hold `CREATE`."""
    try:
        applied = run_migrations(dsn, target=target)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    if applied:
        typer.echo(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        typer.echo("Already up to date — no pending migrations.")


@db_app.command(name="rollback")
def db_rollback(
    dsn: str = typer.Option(..., "--dsn", help="PostgreSQL DSN (migration-owning role)"),
    steps: int = typer.Option(
        1, "--steps", help="Number of most-recently-applied migrations to roll back"
    ),
) -> None:
    """Roll back the most recently applied migration(s) (ADR-0011) — schema
    reversibility via each migration's paired `.down.sql`, not a
    data-preserving downgrade. Back up first (docs/guides/backup-restore.md)."""
    try:
        rolled_back = rollback_migrations(dsn, steps=steps)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    if rolled_back:
        typer.echo(f"Rolled back {len(rolled_back)} migration(s): {', '.join(rolled_back)}")
    else:
        typer.echo("Nothing to roll back — schema_migrations is empty.")


@db_app.command(name="status")
def db_status(
    dsn: str = typer.Option(..., "--dsn", help="PostgreSQL DSN"),
) -> None:
    """List applied migration versions (ADR-0011)."""
    try:
        versions = migration_status(dsn)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    if versions:
        typer.echo(f"Applied migrations: {', '.join(versions)}")
    else:
        typer.echo("No migrations applied yet.")


@audit_app.command(name="count-expired")
def audit_count_expired(
    dsn: str = typer.Option(..., "--dsn", help="PostgreSQL DSN"),
) -> None:
    """Report how many audit_events rows are past their retention_days
    window, without deleting anything (ADR-0011). Safe to run under the
    application's own INSERT/SELECT-only role — see
    docs/guides/postgres-permissions.md."""
    try:
        count = count_expired_audit_events(dsn)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    typer.echo(f"{count} audit event(s) past retention.")


@audit_app.command(name="purge")
def audit_purge(
    dsn: str = typer.Option(
        ...,
        "--dsn",
        help="PostgreSQL DSN — the retention-job role (docs/guides/postgres-permissions.md), "
        "never the application's own runtime DSN",
    ),
) -> None:
    """Permanently delete every audit_events row past its retention_days
    window (ADR-0011). Deliberately `--dsn`, never `--manifest`: building
    this sink from a manifest's `audit_sink:` block would silently reuse
    the live application's own DSN, which should never have DELETE
    privilege (docs/guides/postgres-permissions.md). Irreversible — this is
    real audit-trail deletion, not a dry run; use `audit count-expired`
    first to preview."""
    try:
        deleted = purge_expired_audit_events(dsn)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    typer.echo(f"Purged {deleted} expired audit event(s).")


@feedback_app.command(name="count-expired")
def feedback_count_expired(
    dsn: str = typer.Option(..., "--dsn", help="PostgreSQL DSN"),
) -> None:
    """Report how many feedback rows are past their retention_days window,
    without deleting anything (ADR-0014). Safe to run under the
    application's own INSERT/SELECT-only role."""
    try:
        count = count_expired_feedback(dsn)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    typer.echo(f"{count} feedback record(s) past retention.")


@feedback_app.command(name="purge")
def feedback_purge(
    dsn: str = typer.Option(
        ...,
        "--dsn",
        help="PostgreSQL DSN — the retention-job role, never the application's own runtime DSN",
    ),
) -> None:
    """Permanently delete every feedback row past its retention_days window
    (ADR-0014). Deliberately `--dsn`, never `--manifest` — same reasoning as
    `audit purge`. Irreversible; use `feedback count-expired` first to
    preview."""
    try:
        deleted = purge_expired_feedback(dsn)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    typer.echo(f"Purged {deleted} expired feedback record(s).")


@review_app.command(name="list-pending")
def review_list_pending(
    dsn: str = typer.Option(..., "--dsn", help="PostgreSQL DSN"),
) -> None:
    """List unresolved review items (ADR-0014)."""
    try:
        items = list_pending_review_items(dsn)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    if not items:
        typer.echo("No pending review items.")
        return
    for item in items:
        typer.echo(
            f"{item['id']}  answer_id={item['answer_id']}  reason={item['reason']!r}  "
            f"confidence={item['confidence']}"
        )


@review_app.command(name="resolve")
def review_resolve(
    item_id: str = typer.Option(..., "--item-id"),
    approved: bool = typer.Option(..., "--approved/--rejected"),
    reviewer: str = typer.Option(..., "--reviewer"),
    dsn: str = typer.Option(..., "--dsn", help="PostgreSQL DSN"),
) -> None:
    """Resolve one pending review item (ADR-0014). Raises an error if
    `item_id` does not exist — see `ReviewQueue.resolve()`."""
    try:
        resolve_review_item(dsn, item_id, approved=approved, reviewer=reviewer)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    typer.echo(f"Resolved {item_id} (approved={approved}, reviewer={reviewer}).")


@review_app.command(name="count-expired")
def review_count_expired(
    dsn: str = typer.Option(..., "--dsn", help="PostgreSQL DSN"),
) -> None:
    """Report how many review_items rows are past their retention_days
    window, without deleting anything (ADR-0014)."""
    try:
        count = count_expired_review_items(dsn)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    typer.echo(f"{count} review item(s) past retention.")


@review_app.command(name="purge")
def review_purge(
    dsn: str = typer.Option(
        ...,
        "--dsn",
        help="PostgreSQL DSN — the retention-job role, never the application's own runtime DSN",
    ),
) -> None:
    """Permanently delete every review_items row past its retention_days
    window (ADR-0014), resolved or not — retention is a data-age policy,
    not a resolution-status one. Irreversible; use `review count-expired`
    first to preview."""
    try:
        deleted = purge_expired_review_items(dsn)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    typer.echo(f"Purged {deleted} expired review item(s).")
