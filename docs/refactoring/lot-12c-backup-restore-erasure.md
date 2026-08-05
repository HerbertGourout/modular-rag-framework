# Lot 12c — Backup, Restore, Rebuild-from-Source, Right-to-Erasure Proof

**Status:** COMPLETE
**Date:** 2026-08-05
**Depends on:** Lot 12b (index schema to version against; `RepairResult.unresolved_missing` is
the concrete case `rebuild_document()` exists to resolve).

## What was done

Per `docs/refactoring-plan.md`: "Implement backup, restore, rebuild-from-source, and
right-to-erasure proof (including a verified restore exercise, not just a backup that has never
been tested)."

### Backup / restore — the lifecycle ledger

- **`contracts/lifecycle.py`**: two new `LifecycleLedger` Protocol methods — `export_all()` (every
  record, *including* tombstoned ones — `list_active()`, from Lot 12b, deliberately excludes them,
  which would make right-to-erasure proof unverifiable after a restore if used for backup) and
  `restore_record()` (writes a record back verbatim: no version bump, no timestamp
  recomputation — distinct from `record_ingested()`, which is for the normal ingest flow).
  Implemented in both `InMemoryLifecycleLedger` and `PostgresLifecycleLedger`.
- **`ingestion/lifecycle/backup.py`**: `backup_ledger()` (JSON serialize via `export_all()`) /
  `restore_ledger()` (JSON deserialize via `restore_record()` per entry). Portable,
  implementation-agnostic snapshot format — explicitly **not** a replacement for PostgreSQL's own
  `pg_dump`/`pg_restore` on the `document_lifecycle` table, which is what a production deployment
  should actually rely on for disaster recovery (see "Not executed here" below).
- **The actual verified restore exercise** (not just "backup ran without raising"):
  `tests/unit/ingestion/lifecycle/test_backup.py::test_backup_then_restore_round_trips_active_and_tombstoned_records`
  backs up a ledger containing both active and tombstoned records, restores into a **fresh, empty**
  `InMemoryLifecycleLedger` instance, and asserts the restored state matches the source record-for-
  record — including confirming the target ledger was genuinely empty before the restore, so the
  test can't pass by accident.

### Rebuild-from-source

- **`RAGEngine.rebuild_document(document)`** (new): forces a full re-chunk/re-embed/re-index,
  bypassing `ingest()`'s idempotency skip entirely. The scenario this exists for: the
  `lifecycle_ledger` believes a document is indexed (its `content_hash` matches), but the actual
  store has lost the chunks — exactly what `orchestration.reconciliation.IndexReconciler`'s
  `RepairResult.unresolved_missing` (Lot 12b) reports and *cannot* auto-repair, since the
  reconciler only has chunk ids, never content. `rebuild_document()` is the other half of that
  story: given the caller re-supplies the original `Document`, it deletes whatever stale chunks
  the ledger still points at, re-indexes fresh ones, and updates the ledger record. Requires a
  configured `lifecycle_ledger` (raises `ConfigurationError` otherwise, same pattern as
  `delete_document()`).

### Right-to-erasure proof

- **`contracts/erasure.py`** (new): `ErasureProof` — `chunk_ids_removed`, and, critically,
  `verified_absent_from_vector`/`verified_absent_from_lexical` (`bool | None`, not just `bool`):
  `None` means "this store doesn't support `list_ids()`, so absence could not be checked" — never
  conflated with `True` ("checked and confirmed gone"). `fully_verified` is `True` only when every
  store that *could* be checked came back clean; an unverifiable store doesn't count as failure,
  but also isn't silently treated as proof.
- **`RAGEngine.erase_document(document_key)`** (new): calls the existing `delete_document()` (Lot
  12a — tombstones the ledger, deletes from both stores), then **re-checks** `indexer.list_ids()`
  and (if supported) `retriever.list_ids()` *after* deletion to confirm the removed ids are
  actually absent — proof, not just trust that the `delete()` calls didn't raise an exception. A
  `proof_hash` (SHA-256 of `document_key` + sorted removed ids + timestamp) gives a verifiable,
  tamper-evident fingerprint of the erasure event. `delete_document()` itself is unchanged —
  `erase_document()` is purely additive, consistent with every other lot's precedent this session.

## What "not just a backup that has never been tested" actually required

The plan's own phrasing is a direct callback to a real, common failure mode: a backup procedure
that has genuinely never been exercised end-to-end. This lot's test suite deliberately restores
into a *fresh* ledger instance rather than checking the source ledger's own state after backing it
up (which would prove nothing about restore correctness at all) — the distinction between "backup
ran" and "restore actually reconstructs the state" is the whole point, and the test is structured
to make that distinction impossible to fake.

## Not executed here (infrastructure-blocked, documented instead)

This sandboxed environment has no live PostgreSQL or Qdrant instance (consistent with every
Postgres/Qdrant integration test written across this whole programme). What's genuinely blocked
vs. what's covered:

- **`InMemoryLifecycleLedger` backup/restore**: fully implemented *and* verified above — this is
  real, executed, passing code, not a stub.
- **`PostgresLifecycleLedger.export_all()`/`restore_record()`**: implemented, with integration
  tests written (`tests/integration/test_postgres_lifecycle_ledger.py`) but not executed here — same
  status as every other Postgres integration test this session.
- **Production PostgreSQL backup/restore procedure** (documented, not new code): use `pg_dump
  --table=document_lifecycle --table=audit_events` for a disaster-recovery-grade backup, and
  `pg_restore` (or `psql < dump.sql` for plain-text dumps) to restore. This is standard operational
  practice for the two Postgres-backed tables this programme has introduced (Lot 10's audit store,
  this lot's lifecycle ledger) — not reimplemented here, since PostgreSQL's own tooling already
  does this correctly and reinventing it would be pure risk. Owned by Lot 16c's deployment
  runbooks, which is where this procedure should be written down as an operational document, not
  as Python code.
- **Qdrant vector-data backup/restore**: Qdrant has a native snapshot API
  (`PUT /collections/{name}/snapshots`, `POST /collections/{name}/snapshots/upload`) for exactly
  this. Not wrapped in a new `QdrantStore` method here — same reasoning as PostgreSQL: this is
  infrastructure-level backup tooling, not something `QdrantStore`'s Python interface needs to
  reimplement, and evaluating/wrapping it usefully requires a live Qdrant to verify against, which
  this environment doesn't have. Flagged for Lot 16c alongside the PostgreSQL procedure.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 457 tests total (375 unit + 82 contract, up from 441 at Lot 12b).
- mypy baseline unchanged at 34.
- `rebuild_document()`/`erase_document()` both tested against real `InMemoryLifecycleLedger` +
  fake indexer/retriever (not mocks) already established in `test_engine.py`.

## Lot 12c acceptance (per its own description in `docs/refactoring-plan.md`)

"Implement backup, restore, rebuild-from-source, and right-to-erasure proof (including a verified
restore exercise, not just a backup that has never been tested)" — all four delivered for the
lifecycle ledger and the coordinated index-deletion path; production PostgreSQL/Qdrant-native
backup tooling documented as the correct mechanism for those two systems specifically, deferred to
Lot 16c's runbooks as operational (not code) content.

This completes Phase C (Lots 11a-c, 12a-c) in full.

## Next

Phase D: Lot 13 (quality/measurement plane — corrects `ExactMatchEvaluator`'s naming and
`BenchmarkRunner`'s failure-masking, both characterized in Lot 4 and still open).
