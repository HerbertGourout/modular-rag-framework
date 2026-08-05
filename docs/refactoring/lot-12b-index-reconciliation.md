# Lot 12b — Index Schema/Version, Reconciliation, and the BM25 Correctness Fix

**Status:** COMPLETE
**Date:** 2026-08-05
**Depends on:** Lot 12a (`LifecycleLedger`/`DocumentRecord` — the source of truth reconciliation
checks against), Lot 11b (`tenant_id` fields — the QdrantStore bug fixed here directly undermined
Lot 11b's tenant isolation for the real vector-store path).

The plan flagged this as "the largest sub-lot in Phase C — consider a mid-lot checkpoint rather
than one large acceptance gate." It ended up covering five distinct, individually-testable pieces;
recorded together here since none is meaningful without the others, but each has its own tests and
each is independently revertable.

## What was done

Per `docs/refactoring-plan.md`: "Define index schema/version; make vector/lexical writes atomic or
reconcilable; implement the reconciliation job that detects and repairs BM25/vector divergence."

### 1. Index schema/version

- **`contracts/lifecycle.py`**: `INDEX_SCHEMA_VERSION = "1.0"` constant, `DocumentRecord.schema_version`
  field (default to the constant). Carried per-record, not globally, so a ledger can hold documents
  indexed under different schema versions during a rolling migration — deliberately not a single
  global version flag.

### 2. `Indexer.list_ids()` — the prerequisite for detecting anything

- **`contracts/indexing.py`**: added `list_ids() -> list[str]` to the `Indexer` Protocol.
- **`QdrantStore.list_ids()`**: implemented via Qdrant's `scroll` API (paginated, no
  vectors/payload fetched).
- **`BM25Retriever.list_ids()`** and **`HybridRetriever.list_ids()`** (delegating to the BM25
  side): duck-typed, not Protocol-enforced (same pattern as `delete()`/`clear()` from Lot 12a) —
  no `Retriever` Protocol change, since not every retriever needs to support reconciliation.

### 3. `IndexReconciler` — detection and (partial) repair

- **`contracts/reconciliation.py`** (new): `DocumentDivergence` (a document whose ledger-expected
  chunk ids are missing from vector and/or lexical storage), `ReconciliationReport`
  (`divergences` + `orphaned_in_vector`/`orphaned_in_lexical` — ids present in a store but expected
  by no active document), `RepairResult`. No Protocol here on purpose: unlike `AuditSink`/
  `LifecycleLedger`, reconciliation is a single orchestration-level job operating on
  already-Protocol'd components, not itself a swappable backend.
- **`orchestration/reconciliation.py`**: `IndexReconciler(container)`.
  - `check()`: treats `LifecycleLedger.list_active()`'s `chunk_ids` as ground truth, compares
    against `Container.indexer.list_ids()` and the retriever's `list_ids()` (if it has one — a
    retriever without one is treated as having nothing indexed, which correctly surfaces as "100%
    missing in lexical" rather than silently skipping the check). Requires a configured
    `lifecycle_ledger` — raises `ConfigurationError` otherwise, same pattern as
    `RAGEngine.delete_document()` (Lot 12a).
  - `repair()`: **only removes orphans** — pure deletion, no content regeneration needed, so it's
    safe to automate. Missing chunks are *not* auto-repaired: fabricating a placeholder
    embedding/BM25 entry to silence the divergence would be actively wrong, since the reconciler
    has no access to the chunk's original content (the ledger stores ids, not content). Missing
    entries are returned as `unresolved_missing`, explicitly deferred to Lot 12c's
    rebuild-from-source.
  - **`LifecycleLedger.list_active()`** (new Protocol method, both implementations updated):
    `get()` alone answers "what's the state of *one* document"; reconciliation needs "what's the
    state of *every* active document," which didn't exist before this lot.

### 4. The BM25 small-corpus scoring bug — actually fixed, not just characterized

Found in Lot 4, explicitly assigned to this lot in the plan's own gap table. `rank_bm25`'s IDF term
goes zero or negative when a query term appears in most/all documents of a small corpus — trivial
with 1-2 chunks indexed. The old `if score > 0` filter then silently dropped a chunk that was the
best, or only, lexical match for the query. `BM25Retriever.retrieve()` now gates inclusion on
genuine lexical token overlap (query and chunk share at least one token) instead of score sign —
the chunk from the small-corpus regression test is now correctly returned with a *negative* score,
while a chunk with zero term overlap is still correctly excluded regardless of what BM25's raw
score would be.

### 5. The QdrantStore tenant_id bug — a real gap found while building `list_ids()`

While touching `qdrant_store.py`, found that `index()` never wrote `chunk.tenant_id` into the
Qdrant payload, and `retrieve_by_vector()` never reconstructed it — meaning **every chunk
round-tripped through the real Qdrant store came back with `tenant_id=None`**, silently defeating
Lot 11b's `TenantIsolationPolicy.filter_chunks()` for the one vector store this framework actually
ships an adapter for (the in-memory fakes used in unit tests never had this bug, which is why nine
Lot 11b tests all passed while this was broken). Fixed:
- `tenant_id` now written to and read back from the Qdrant payload.
- **Query-time filtering added**: `QdrantStore.retrieve_by_vector(vector, k, tenant_id=...)`
  applies a Qdrant payload `Filter` when `tenant_id` is given, and `VectorRetriever.retrieve()`
  passes `query.tenant_id` through automatically. This resolves the "evaluate query-time
  partitioning" follow-up explicitly flagged as open in Lot 11b's decision record — evaluated and
  implemented as a defense-in-depth layer on top of `TenantIsolationPolicy`, which remains the
  fail-closed backstop (a store that doesn't honor the filter, or a caller that doesn't pass
  `tenant_id`, still gets the post-retrieval filter).
- Omitting `tenant_id` applies no filter — exact backward-compatible default, proven by a
  dedicated regression test.

## "Atomic or reconcilable"

The plan accepted either. True atomicity across Qdrant and an in-memory BM25 index (two unrelated
storage engines) isn't practical for V1 — this lot delivers the "reconcilable" half explicitly,
documented here as the deliberate choice rather than an oversight.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 441 tests total (361 unit + 80 contract, up from 418 at Lot 12a).
- mypy baseline **ratcheted down 35 → 34**: the BM25 `retrieve()` rewrite's type-narrowing
  incidentally fixed one pre-existing error; the baseline file was updated to lock the improvement
  in, per its own "reduce deliberately, never raise" rule.
- `tests/integration/test_qdrant_store.py` gained `list_ids()`, `tenant_id` round-trip, and
  query-time-filter tests (written, reviewed, not executed here — no local Qdrant, same status as
  every other integration test this session).
- `tests/integration/test_postgres_lifecycle_ledger.py` gained a `list_active()` test, same status.
- The reconciler's "no fabrication" property has a dedicated regression test
  (`test_repair_does_not_invent_content_for_missing_chunks`) proving a genuinely missing chunk is
  reported, not silently invented.

## Known limitations (not closed by this lot)

- **Rebuild-from-source for missing chunks** is Lot 12c's job, not this one's — `unresolved_missing`
  exists specifically to hand off to it.
- **`IndexReconciler` is not scheduled anywhere** — it's a callable job (`check()`/`repair()`), not
  a cron/background task. Wiring it into a periodic runner is deployment-runbook territory
  (Lot 16c), not domain logic.
- **No manifest/registry wiring** for any of this lot's new optional pieces, consistent with every
  other lot's precedent this session.

## Lot 12b acceptance (per its own description in `docs/refactoring-plan.md`)

"Define index schema/version; make vector/lexical writes atomic or reconcilable; implement the
reconciliation job that detects and repairs BM25/vector divergence" — schema versioning delivered
(`INDEX_SCHEMA_VERSION`/`DocumentRecord.schema_version`), reconcilable (not atomic, by deliberate
choice) writes, and a reconciliation job that detects both divergence directions and repairs the
safely-automatable one (orphans).

## Next

Lot 12c (backup, restore, rebuild-from-source, right-to-erasure proof — "including a verified
restore exercise, not just a backup that has never been tested"). Depends on this lot's index
schema existing to version backups against, and directly picks up `RepairResult.unresolved_missing`
as the concrete case rebuild-from-source needs to handle.
