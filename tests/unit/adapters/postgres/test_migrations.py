"""Unit tests for adapters/postgres/migrations.py (ADR-0011 — PostgreSQL
migrations, connection pooling, and audit retention). Service-free coverage
using a hand-built fake connection (no real psycopg installed in this dev
environment) plus REAL `.sql` files written to `tmp_path` — `discover_migrations()`
genuinely reads from disk, so faking the filesystem too would leave that
logic untested. The actual `CREATE`/`DROP` round-trip and the
`pg_advisory_xact_lock` concurrency guarantee against a real, second
process need live PostgreSQL — covered by
`tests/integration/test_postgres_migrations.py` instead.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from modular_rag.adapters.postgres.migrations import (
    MigrationRunner,
    default_migrations_dir,
    discover_migrations,
)
from modular_rag.core.errors import ConfigurationError, StorageError


def _write_migration(tmp_path: Path, version: str, name: str, up: str, down: str) -> None:
    (tmp_path / f"{version}_{name}.up.sql").write_text(up, encoding="utf-8")
    (tmp_path / f"{version}_{name}.down.sql").write_text(down, encoding="utf-8")


# ---------------------------------------------------------------------------
# discover_migrations() — real filesystem, tmp_path.
# ---------------------------------------------------------------------------


def test_discover_migrations_pairs_up_and_down_files_sorted_by_version(tmp_path):
    _write_migration(tmp_path, "0002", "second", "CREATE TABLE b();", "DROP TABLE b;")
    _write_migration(tmp_path, "0001", "first", "CREATE TABLE a();", "DROP TABLE a;")

    migrations = discover_migrations(tmp_path)

    assert [m.version for m in migrations] == ["0001", "0002"]
    assert migrations[0].name == "first"
    assert migrations[0].up_sql == "CREATE TABLE a();"
    assert migrations[0].down_sql == "DROP TABLE a;"


def test_discover_migrations_rejects_a_file_not_matching_the_naming_pattern(tmp_path):
    (tmp_path / "not_a_migration.sql").write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="does not match"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_an_up_file_missing_its_down_file(tmp_path):
    """test-specialist review (pre-implementation): fails at discovery
    time, before any migration is ever applied — not later, the first time
    a rollback happens to be attempted."""
    (tmp_path / "0001_no_down.up.sql").write_text("CREATE TABLE a();", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="has no matching"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_a_duplicate_up_version(tmp_path):
    (tmp_path / "0001_first.up.sql").write_text("CREATE TABLE a();", encoding="utf-8")
    (tmp_path / "0001_first.down.sql").write_text("DROP TABLE a;", encoding="utf-8")
    (tmp_path / "0001_also_first.up.sql").write_text("CREATE TABLE b();", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Duplicate up migration version"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_a_duplicate_down_version(tmp_path):
    """Codex review HIGH-001 (post-implementation): down-files are now
    indexed and duplicate-checked exactly like up-files, not merged
    silently by whichever one the filesystem glob happens to list last."""
    (tmp_path / "0001_first.up.sql").write_text("CREATE TABLE a();", encoding="utf-8")
    (tmp_path / "0001_first.down.sql").write_text("DROP TABLE a;", encoding="utf-8")
    (tmp_path / "0001_second_name.down.sql").write_text("DROP TABLE b;", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Duplicate down migration version"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_a_down_file_paired_with_a_different_named_up_file(tmp_path):
    """Codex review HIGH-001 (post-implementation) — the core finding:
    `0002_audit_events.up.sql` must never silently pair with
    `0002_something_else.down.sql` just because they share a version
    number. A rollback would then run a `.down.sql` written for a
    completely different migration."""
    (tmp_path / "0002_audit_events.up.sql").write_text("CREATE TABLE audit();", encoding="utf-8")
    (tmp_path / "0002_something_else.down.sql").write_text(
        "DROP TABLE unrelated_and_wrong;", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match="different names"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_an_orphaned_down_file(tmp_path):
    (tmp_path / "0001_orphan.down.sql").write_text("DROP TABLE a;", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="no matching"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_a_version_that_is_not_exactly_four_digits(tmp_path):
    """Codex review HIGH-001 (post-implementation): the ADR's own `NNNN_name`
    naming convention was documented but never actually enforced — any
    digit-length version was silently accepted."""
    (tmp_path / "1_first.up.sql").write_text("CREATE TABLE a();", encoding="utf-8")
    (tmp_path / "1_first.down.sql").write_text("DROP TABLE a;", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="does not match"):
        discover_migrations(tmp_path)


def test_discover_migrations_on_an_empty_directory_returns_nothing(tmp_path):
    assert discover_migrations(tmp_path) == []


def test_default_migrations_dir_resolves_to_a_real_directory_with_the_shipped_migrations():
    """Sanity check that `importlib.resources` actually finds the packaged
    `sql/` directory this repo ships (0001/0002/0003) — not a fake, this
    proves the real packaging path works from a dev checkout."""
    migrations_dir = default_migrations_dir()

    assert migrations_dir.is_dir()
    versions = {m.version for m in discover_migrations(migrations_dir)}
    assert {"0001", "0002", "0003"} <= versions


# ---------------------------------------------------------------------------
# MigrationRunner — fake psycopg connection (no real database).
# ---------------------------------------------------------------------------


def _install_fake_psycopg_module(monkeypatch, connect):
    """See adapters' own identical helper (e.g.
    tests/unit/adapters/lifecycle/test_postgres_ledger.py) for the full
    rationale — `psycopg` is not installed in this dev environment."""
    import sys
    import types

    fake_module = types.ModuleType("psycopg")
    fake_module.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)


class _FakeMigrationCursor:
    def __init__(self, rows=None) -> None:
        self._rows = rows if rows is not None else []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeMigrationConn:
    """A minimal in-memory stand-in for a real, non-autocommit psycopg
    connection — tracks every statement executed and maintains its own
    `schema_migrations` state, so `MigrationRunner`'s logic (lock, apply in
    order, record, skip already-applied, rollback) is exercised end to end
    without a real database. Raises on `execute()` for a SQL string
    containing the sentinel `-- FAIL --`, to test failure wrapping."""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.committed = False
        self.lock_acquired = False
        self.schema_migrations_table_exists = False
        self._schema_migrations: dict[str, tuple[str, object]] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append(sql)
        text = sql.strip()
        lowered = text.lower()
        if "-- fail --" in lowered:
            raise RuntimeError("simulated migration failure")
        if lowered.startswith("select pg_advisory_xact_lock"):
            self.lock_acquired = True
            return _FakeMigrationCursor()
        if lowered.startswith("select to_regclass('schema_migrations')"):
            return _FakeMigrationCursor(rows=[(self.schema_migrations_table_exists,)])
        if lowered.startswith("create table if not exists schema_migrations"):
            self.schema_migrations_table_exists = True
            return _FakeMigrationCursor()
        if text == "SELECT version FROM schema_migrations":
            return _FakeMigrationCursor(rows=[(v,) for v in self._schema_migrations])
        if lowered.startswith("insert into schema_migrations"):
            version, name, applied_at = params
            self._schema_migrations[version] = (name, applied_at)
            return _FakeMigrationCursor()
        if lowered.startswith("delete from schema_migrations"):
            (version,) = params
            self._schema_migrations.pop(version, None)
            return _FakeMigrationCursor()
        return _FakeMigrationCursor()  # a real migration's up/down SQL

    def commit(self) -> None:
        self.committed = True


def test_migrate_applies_pending_migrations_in_order(tmp_path, monkeypatch):
    _write_migration(tmp_path, "0001", "first", "CREATE TABLE a();", "DROP TABLE a;")
    _write_migration(tmp_path, "0002", "second", "CREATE TABLE b();", "DROP TABLE b;")
    conn = _FakeMigrationConn()
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: conn)
    runner = MigrationRunner("postgresql://unused/unused", migrations_dir=tmp_path)

    applied = runner.migrate()

    assert applied == ["0001", "0002"]
    assert conn.executed.index("CREATE TABLE a();") < conn.executed.index("CREATE TABLE b();")
    assert conn.committed is True


def test_migrate_acquires_the_advisory_lock_before_reading_schema_migrations(tmp_path, monkeypatch):
    """test-specialist review (pre-implementation): the lock must be taken
    before the pending-migration check, not after."""
    _write_migration(tmp_path, "0001", "first", "CREATE TABLE a();", "DROP TABLE a;")
    conn = _FakeMigrationConn()
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: conn)
    runner = MigrationRunner("postgresql://unused/unused", migrations_dir=tmp_path)

    runner.migrate()

    lock_index = next(
        i for i, sql in enumerate(conn.executed) if "pg_advisory_xact_lock" in sql.lower()
    )
    select_index = next(
        i
        for i, sql in enumerate(conn.executed)
        if sql.strip() == "SELECT version FROM schema_migrations"
    )
    assert lock_index < select_index


def test_migrate_connects_with_autocommit_false(tmp_path, monkeypatch):
    """test-specialist review (pre-implementation): `pg_advisory_xact_lock`
    is transaction-scoped — on an autocommit connection it would release
    the instant the lock-acquiring statement's own implicit transaction
    ends, making it a no-op."""
    _write_migration(tmp_path, "0001", "first", "CREATE TABLE a();", "DROP TABLE a;")
    captured_kwargs: dict = {}

    def fake_connect(dsn, **kwargs):
        captured_kwargs.update(kwargs)
        return _FakeMigrationConn()

    _install_fake_psycopg_module(monkeypatch, fake_connect)
    runner = MigrationRunner("postgresql://unused/unused", migrations_dir=tmp_path)

    runner.migrate()

    assert captured_kwargs["autocommit"] is False


def test_migrate_is_idempotent_and_executes_no_ddl_when_already_applied(tmp_path, monkeypatch):
    _write_migration(tmp_path, "0001", "first", "CREATE TABLE a();", "DROP TABLE a;")
    conn = _FakeMigrationConn()
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: conn)
    runner = MigrationRunner("postgresql://unused/unused", migrations_dir=tmp_path)
    runner.migrate()
    conn.executed.clear()

    second_call_applied = runner.migrate()

    assert second_call_applied == []
    assert "CREATE TABLE a();" not in conn.executed


def test_migrate_respects_an_explicit_target_version(tmp_path, monkeypatch):
    _write_migration(tmp_path, "0001", "first", "CREATE TABLE a();", "DROP TABLE a;")
    _write_migration(tmp_path, "0002", "second", "CREATE TABLE b();", "DROP TABLE b;")
    conn = _FakeMigrationConn()
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: conn)
    runner = MigrationRunner("postgresql://unused/unused", migrations_dir=tmp_path)

    applied = runner.migrate(target="0001")

    assert applied == ["0001"]
    assert "CREATE TABLE b();" not in conn.executed


def test_migrate_rejects_a_target_that_does_not_match_any_discovered_migration(
    tmp_path, monkeypatch
):
    """Codex review MEDIUM-001 (post-implementation): the previous version
    only compared `target` lexically inside the apply loop
    (`migration.version > target`) — a target lexically past every known
    version (`"9999"`) silently applied *everything* and returned success;
    a target lexically before the first version silently applied *nothing*
    and also returned success ("Already up to date"). Neither is what an
    operator pinning a deployment to a specific, existing schema version
    intends. Must fail before ever opening a connection."""
    _write_migration(tmp_path, "0001", "first", "CREATE TABLE a();", "DROP TABLE a;")
    conn = _FakeMigrationConn()
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: conn)
    runner = MigrationRunner("postgresql://unused/unused", migrations_dir=tmp_path)

    with pytest.raises(ConfigurationError, match="does not match any discovered"):
        runner.migrate(target="9999")

    assert conn.executed == []  # never connected -- validated before any DB round-trip


def test_migrate_rejects_a_target_lexically_before_the_first_migration(tmp_path, monkeypatch):
    _write_migration(tmp_path, "0002", "second", "CREATE TABLE b();", "DROP TABLE b;")
    conn = _FakeMigrationConn()
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: conn)
    runner = MigrationRunner("postgresql://unused/unused", migrations_dir=tmp_path)

    with pytest.raises(ConfigurationError, match="does not match any discovered"):
        runner.migrate(target="0001")


def test_migrate_wraps_a_failing_migration_in_a_storage_error(tmp_path, monkeypatch):
    _write_migration(tmp_path, "0001", "first", "CREATE TABLE a(); -- FAIL --", "DROP TABLE a;")
    conn = _FakeMigrationConn()
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: conn)
    runner = MigrationRunner("postgresql://unused/unused", migrations_dir=tmp_path)

    with pytest.raises(StorageError, match="0001_first failed"):
        runner.migrate()


def test_rollback_reverses_the_most_recently_applied_migrations_in_reverse_order(
    tmp_path, monkeypatch
):
    _write_migration(tmp_path, "0001", "first", "CREATE TABLE a();", "DROP TABLE a;")
    _write_migration(tmp_path, "0002", "second", "CREATE TABLE b();", "DROP TABLE b;")
    conn = _FakeMigrationConn()
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: conn)
    runner = MigrationRunner("postgresql://unused/unused", migrations_dir=tmp_path)
    runner.migrate()

    rolled_back = runner.rollback(steps=2)

    assert rolled_back == ["0002", "0001"]
    assert conn.executed.index("DROP TABLE b;") < conn.executed.index("DROP TABLE a;")
    assert runner.applied_versions() == []


def test_rollback_defaults_to_one_step():
    with pytest.raises(ConfigurationError):
        MigrationRunner("postgresql://unused/unused").rollback(steps=0)


def test_applied_versions_is_read_only_and_does_not_apply_anything(tmp_path, monkeypatch):
    _write_migration(tmp_path, "0001", "first", "CREATE TABLE a();", "DROP TABLE a;")
    conn = _FakeMigrationConn()
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: conn)
    runner = MigrationRunner("postgresql://unused/unused", migrations_dir=tmp_path)

    versions = runner.applied_versions()

    assert versions == []
    assert "CREATE TABLE a();" not in conn.executed


def test_applied_versions_never_creates_the_tracking_table_on_a_virgin_database(
    tmp_path, monkeypatch
):
    """Codex review, remaining-risks item (post-implementation): the
    previous version called `_ensure_schema_migrations_table()`
    unconditionally — genuinely running `CREATE TABLE IF NOT EXISTS` (and
    committing it) even for a pure status check, contradicting its own
    "read-only" docstring and requiring schema `CREATE` privilege just to
    ask "what's applied?" on a database nothing has touched yet."""
    conn = _FakeMigrationConn()
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: conn)
    runner = MigrationRunner("postgresql://unused/unused")

    versions = runner.applied_versions()

    assert versions == []
    assert conn.schema_migrations_table_exists is False
    assert not any("create table" in sql.lower() for sql in conn.executed)
