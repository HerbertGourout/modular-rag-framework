"""PostgreSQL schema migration runner (ADR-0011 — PostgreSQL migrations,
connection pooling, and audit retention).

Shared infra helper for both PostgreSQL adapters (`adapters/lifecycle/
postgres_ledger.py`, `adapters/audit/postgres_sink.py`) — not itself an
adapter: no Protocol implementation, not registered in any manifest, the
same "operates on already-Protocol'd things, not a swappable backend"
reasoning `orchestration.reconciliation.IndexReconciler` documents for why
it has no Protocol either (see `contracts/reconciliation.py`'s module
docstring). Reviewed with architecture-reviewer before implementation: a
shared *infrastructure* helper importing only `core/` is not the
"adapters never import each other" violation that rule exists to prevent
(that rule is about not coupling two *backend choices* for one capability,
e.g. Qdrant importing from Postgres) — both Postgres adapters already
share the same physical database in every shipped deployment shape.

`psycopg` is imported lazily per `.claude/.instructions.md` §4, same
"opt-in infrastructure" precedent as the two adapters this module serves.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from modular_rag.core.errors import ConfigurationError, StorageError

if TYPE_CHECKING:
    import psycopg

# Codex review HIGH-001 (post-implementation): tightened from `\d+` to `\d{4}` —
# the ADR's own naming convention (`NNNN_name`) was documented but never actually
# enforced; a version of any digit-length was silently accepted.
_VERSION_NAME_PATTERN = re.compile(r"^(\d{4})_([A-Za-z0-9_]+)\.(up|down)\.sql$")

# Codex review / test-specialist review (pre-implementation, ADR-0011): a
# single, fixed advisory-lock key shared by every migration run against a
# given database, regardless of which caller triggered it (an adapter's
# `auto_migrate=True` lazy path, or the `mrag db migrate` CLI command) — so
# two processes starting concurrently can never apply the same migration
# twice. Advisory locks are scoped per *database session*, not per table,
# so one arbitrary stable constant is sufficient; it does not need to be
# derived from anything migration-specific.
_MIGRATION_LOCK_KEY = 875_321_001


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    up_sql: str
    down_sql: str


def default_migrations_dir() -> Path:
    """The packaged `sql/` directory shipped inside this subpackage,
    resolved via `importlib.resources` so it works identically from a dev
    checkout and from an installed wheel. A top-level repo-root
    `migrations/` directory (considered initially) would NOT ship in
    `pip install modular-rag[postgres]` — `pyproject.toml`'s
    `[tool.hatch.build.targets.wheel]` only packages `src/modular_rag`."""
    from importlib.resources import files

    return Path(str(files("modular_rag.adapters.postgres") / "sql"))


def discover_migrations(migrations_dir: Path) -> list[Migration]:
    """Pair up `NNNN_name.up.sql` / `NNNN_name.down.sql` files into
    `Migration` records, sorted by version (zero-padded, so lexical order
    matches numeric order). Fails at discovery time, before any migration is
    ever applied, not later when a rollback happens to be attempted for the
    first time (test-specialist review, pre-implementation), for:
    a missing `.down.sql` for an existing `.up.sql`; a duplicate version
    among either `.up.sql` or `.down.sql` files; an orphaned `.down.sql`
    with no matching `.up.sql`; and — Codex review HIGH-001
    (post-implementation) — a `.down.sql` whose *name* doesn't match its
    same-versioned `.up.sql`'s name. The previous version of this function
    indexed down-files by version number alone (`downs[version] = path`),
    so `0002_audit_events.up.sql` paired silently with any
    `0002_whatever_else.down.sql` present — a naming mistake or a stray
    leftover file would associate an unrelated, potentially destructive
    rollback script with a migration it was never written for, undetected
    until the rollback actually ran. Down-files are now indexed by
    `(version, name)` exactly like up-files, and the two must match."""
    ups: dict[str, tuple[str, Path]] = {}
    downs: dict[str, tuple[str, Path]] = {}
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _VERSION_NAME_PATTERN.match(path.name)
        if not match:
            raise ConfigurationError(
                f"Migration file {path.name!r} in {migrations_dir} does not match "
                "the required NNNN_name.(up|down).sql naming pattern (exactly 4 digits)."
            )
        version, name, direction = match.group(1), match.group(2), match.group(3)
        target = ups if direction == "up" else downs
        if version in target:
            raise ConfigurationError(
                f"Duplicate {direction} migration version {version!r} in {migrations_dir} "
                f"({target[version][1].name} and {path.name})."
            )
        target[version] = (name, path)

    orphaned_downs = set(downs) - set(ups)
    if orphaned_downs:
        version = sorted(orphaned_downs)[0]
        orphan_name, orphan_path = downs[version]
        raise ConfigurationError(
            f"{orphan_path.name!r} in {migrations_dir} has no matching "
            f"{version}_{orphan_name}.up.sql — every down-file must pair with an up-file."
        )

    migrations: list[Migration] = []
    for version, (name, up_path) in sorted(ups.items()):
        if version not in downs:
            raise ConfigurationError(
                f"Migration {version}_{name} has no matching {version}_{name}.down.sql "
                f"in {migrations_dir} — every migration must be reversible."
            )
        down_name, down_path = downs[version]
        if down_name != name:
            raise ConfigurationError(
                f"Migration {version}: up-file {up_path.name!r} and down-file "
                f"{down_path.name!r} have different names ({name!r} vs {down_name!r}) — "
                "a down-file must share its up-file's exact name, not just its version "
                "number, so an unrelated file can never be paired with it silently."
            )
        migrations.append(
            Migration(
                version=version,
                name=name,
                up_sql=up_path.read_text(encoding="utf-8"),
                down_sql=down_path.read_text(encoding="utf-8"),
            )
        )
    return migrations


class MigrationRunner:
    """Applies/rolls back versioned SQL migrations against a PostgreSQL
    database, tracked in a `schema_migrations` table this runner creates
    and owns directly — bootstrap bookkeeping, not itself a numbered
    migration (the same self-managed-tracking-table precedent as Flyway/
    Django/Rails migration tooling).

    Deliberately connects on its own, separate from `psycopg_pool.
    ConnectionPool` — migrations run once, rarely, and need a real
    transaction (see `_connect()`'s docstring for why autocommit=True,
    used everywhere else in these adapters, would silently make the
    advisory lock below a no-op); they have no business sharing the
    pool sized and tuned for high-frequency request-path queries.
    """

    def __init__(self, dsn: str, migrations_dir: Path | None = None) -> None:
        self._dsn = dsn
        self._migrations_dir = migrations_dir or default_migrations_dir()

    def _connect(self) -> psycopg.Connection[Any]:
        """A fresh, dedicated, non-autocommit connection.

        Test-specialist review (pre-implementation): non-autocommit is
        required, not cosmetic. `pg_advisory_xact_lock` is
        *transaction-scoped* — it releases the instant its holding
        transaction ends. On an autocommit connection (the convention every
        other query in these two adapters uses) each statement is its own
        implicit transaction, so the lock would release immediately after
        the `SELECT pg_advisory_xact_lock(...)` call itself returns,
        defeating its entire purpose. Every statement in `migrate()`/
        `rollback()` below runs inside the one explicit transaction the
        lock was acquired in, committed exactly once at the end.
        """
        import psycopg

        return psycopg.connect(self._dsn, autocommit=False)

    def migrate(self, target: str | None = None) -> list[str]:
        """Apply every pending migration up to and including `target`
        (default: all discovered migrations). Returns the newly-applied
        version numbers, in application order. A no-op (empty result, no
        connection side effects beyond the lock/transaction itself) if
        every migration is already applied.

        Codex review MEDIUM-001 (post-implementation): `target` is now
        validated against the discovered catalog *before* ever opening a
        connection. The previous version only compared `target` lexically
        inside the loop (`migration.version > target`) — a target lexically
        past every known version (a typo, or a future version not yet
        shipped to this install) silently applied *every* pending
        migration and returned success, while a target lexically before
        the first version silently applied nothing and also returned
        success ("Already up to date"). Neither outcome is what an
        operator pinning a deployment to a specific schema version intends,
        and a scripted `mrag db migrate --target <typo>` had no way to
        detect the mistake from the exit code alone.
        """
        migrations = discover_migrations(self._migrations_dir)
        if target is not None and target not in {m.version for m in migrations}:
            raise ConfigurationError(
                f"migrate() target {target!r} does not match any discovered migration "
                f"version in {self._migrations_dir}. Known versions: "
                f"{sorted(m.version for m in migrations)}."
            )
        applied_versions: list[str] = []
        with self._connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_KEY,))
            self._ensure_schema_migrations_table(conn)
            already_applied = self._applied_versions(conn)
            for migration in migrations:
                if target is not None and migration.version > target:
                    break
                if migration.version in already_applied:
                    continue
                try:
                    conn.execute(migration.up_sql)
                except Exception as exc:
                    raise StorageError(
                        f"Migration {migration.version}_{migration.name} failed: {exc}"
                    ) from exc
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) "
                    "VALUES (%s, %s, %s)",
                    (migration.version, migration.name, datetime.now(UTC)),
                )
                applied_versions.append(migration.version)
            conn.commit()
        return applied_versions

    def rollback(self, steps: int = 1) -> list[str]:
        """Roll back the `steps` most-recently-applied migrations, in
        reverse (newest-first) order, via each migration's paired
        `.down.sql`. "Reasonable rollback" (this lot's acceptance
        criterion) means schema reversibility, not a data-preserving
        downgrade — see each `.down.sql` file's own header comment.
        Returns the version numbers actually rolled back, in the order
        they were rolled back."""
        if steps < 1:
            raise ConfigurationError(f"rollback() steps must be >= 1, got {steps}.")
        migrations_by_version = {m.version: m for m in discover_migrations(self._migrations_dir)}
        rolled_back: list[str] = []
        with self._connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_KEY,))
            self._ensure_schema_migrations_table(conn)
            applied_versions = sorted(self._applied_versions(conn), reverse=True)
            for version in applied_versions[:steps]:
                migration = migrations_by_version.get(version)
                if migration is None:
                    raise ConfigurationError(
                        f"Cannot roll back migration {version}: no matching migration file "
                        f"found in {self._migrations_dir} (schema_migrations records it as "
                        "applied, but its source file is missing)."
                    )
                try:
                    conn.execute(migration.down_sql)
                except Exception as exc:
                    raise StorageError(f"Rollback of migration {version} failed: {exc}") from exc
                conn.execute("DELETE FROM schema_migrations WHERE version = %s", (version,))
                rolled_back.append(version)
            conn.commit()
        return rolled_back

    def applied_versions(self) -> list[str]:
        """Read-only: which migration versions have already been applied,
        sorted. Used by `mrag db status` and by the two adapters'
        `check_health()` (indirectly — see each adapter's own schema-
        existence probe, which queries the target table directly rather
        than going through this heavier, lock-taking method).

        Codex review, remaining-risks item (post-implementation): this
        previously called `_ensure_schema_migrations_table()` unconditionally
        — genuinely creating (and committing) the tracking table via `CREATE
        TABLE IF NOT EXISTS` if it didn't exist yet, contradicting its own
        "read-only" docstring and silently requiring the caller's DSN to hold
        schema `CREATE` privilege just to check status on a virgin database.
        Now checks existence first and returns `[]` without writing anything
        if the table has never been created — `mrag db status` against a
        database no migration has ever touched genuinely needs no more than
        `SELECT` privilege.
        """
        with self._connect() as conn:
            table_exists = conn.execute(
                "SELECT to_regclass('schema_migrations') IS NOT NULL"
            ).fetchone()[0]
            if not table_exists:
                return []
            versions = sorted(self._applied_versions(conn))
            conn.commit()
        return versions

    @staticmethod
    def _ensure_schema_migrations_table(conn: psycopg.Connection[Any]) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL
            )
            """
        )

    @staticmethod
    def _applied_versions(conn: psycopg.Connection[Any]) -> set[str]:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {row[0] for row in rows}
