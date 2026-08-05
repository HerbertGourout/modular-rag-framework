# Lot 12a — Document Lifecycle: Identity, Idempotency, Update, Deletion, Tombstones

**Status:** COMPLETE
**Date:** 2026-08-05
**Depends on:** Lot 11b (`tenant_id` on `Document`/`Chunk`, used in document-key computation),
Lot 10 (PostgreSQL already selected and precedented as the durable-store choice for exactly this
kind of ledger).

## What was done

Per `docs/refactoring-plan.md`: "Define document identity, idempotent ingestion, update, deletion,
and tombstone semantics. This is the domain-level lifecycle contract, independent of any specific
index implementation. The lifecycle/idempotency ledger itself is backed by PostgreSQL, consistent
with Lot 10's audit-store choice."

### Document identity

- **`ingestion/lifecycle/hashing.py`**: `document_key(source, tenant_id)` — a stable SHA256-based
  key derived from `(tenant_id, source)`, deliberately *not* `Document.id` (which stays a random
  UUID per parse, unchanged — nothing that already depends on fresh `Document.id`s per ingest
  call breaks). `content_hash(content)` detects whether a document's content actually changed
  since the last ingest. Tested edge case, not hidden: a tenant literally named `"default"`
  collides with the untenanted (`None`) case, since `None` is internally represented as the
  `"default"` placeholder string before hashing.

### Idempotent ingestion, update, deletion, tombstones

- **`contracts/lifecycle.py`** (new): `DocumentStatus` (`ACTIVE`/`TOMBSTONED`), `DocumentRecord`
  (document_key, tenant_id, content_hash, version, status, `chunk_ids`, timestamps), and the
  `LifecycleLedger` Protocol — deliberately split into `get()` (read, to decide skip/update
  *before* chunking) and `record_ingested()` (write, called *after* chunking/indexing succeed),
  because the caller needs the *old* record's `chunk_ids` to delete stale chunks before it can
  safely write the new ones.
- **`ingestion/lifecycle/in_memory_ledger.py`**: `InMemoryLifecycleLedger` — real reference
  implementation (not a mock).
- **`adapters/lifecycle/postgres_ledger.py`**: `PostgresLifecycleLedger` — durable backend, lazy
  psycopg import (same undeclared-optional-dependency precedent as
  `adapters/audit/postgres_sink.py`, Lot 10), `document_lifecycle` table with an
  `ON CONFLICT (document_key) DO UPDATE` upsert (mutable, unlike the audit store's append-only
  design — a document's row is updated in place as its version/status changes; history across
  versions lives in the audit trail, not here).
- **`Container.lifecycle_ledger`** (new optional property, same precedent as every other optional
  component).
- **`RAGEngine.ingest()`** (rewritten, behavior-preserving when no ledger is configured): with a
  `lifecycle_ledger`, re-ingesting a document whose key+hash both match the ledger's current
  record is skipped entirely (no re-chunk/re-embed/re-index); re-ingesting with the same key but
  different content deletes the previous version's chunks first (via the new
  `_delete_chunk_ids()` helper), then indexes the new ones, then records the new version.
- **`RAGEngine.delete_document(document_key)`** (new — **the method that did not exist before this
  lot**, closing exactly the gap Lot 4 first characterized: "`RAGEngine` has no `delete()` at
  all"). Requires a configured `lifecycle_ledger` (raises `ConfigurationError` otherwise — no
  ledger means no record of which chunk ids belong to the document). Idempotent: deleting an
  already-tombstoned or unknown key returns `0`, not an error.
- **`RAGEngine._delete_chunk_ids()`** (new private helper): calls `Container.indexer.delete(ids)`
  **and** `Container.retriever.delete(ids)` (if the retriever exposes one) — the exact
  coordination Lot 4 found missing ("there is no coordination mechanism to even build on yet").

### Fixing the retrievers to make deletion possible at all

Two structural bugs, both named in `docs/refactoring-plan.md` §2's "Data deletion/update" row,
had to be fixed before `_delete_chunk_ids()` could do anything useful on the lexical side:

- **`BM25Retriever.index()` used to *replace* `self._chunks` on every call**, not append —
  meaning a second `ingest()` call would silently drop the first batch from lexical search
  entirely. It now appends and rebuilds the `BM25Okapi` model from the full corpus each call
  (`rank_bm25` has no incremental-update API, so a full rebuild is the only option). Regression
  test: `tests/unit/retrieval/test_bm25.py::test_index_appends_to_the_previous_corpus` (replaces
  the old characterization test documenting the pre-fix behavior).
- **`BM25Retriever` had no `delete()`/`clear()` at all.** Both added, mirroring `Indexer`'s shape.
- **`HybridRetriever`** gained `delete()`/`clear()`, delegating to its owned `_bm25` side only —
  the vector side is owned separately via `Container.indexer`, which `RAGEngine` already
  coordinates.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 418 tests total (339 unit + 79 contract, up from 388 at Lot 11c).
- mypy baseline unchanged at 35.
- `tests/integration/test_postgres_lifecycle_ledger.py` written and reviewed but not executed in
  this environment (no local PostgreSQL) — same status as the pre-existing Qdrant/Postgres-audit
  integration tests.
- End-to-end proof, not just unit-level: `test_ingest_with_a_lifecycle_ledger_skips_unchanged_content`,
  `test_ingest_with_a_lifecycle_ledger_reindexes_changed_content`, and
  `test_delete_document_removes_chunks_from_indexer_and_retriever` exercise the full
  `RAGEngine.ingest()`/`delete_document()` path against real (non-mocked) `InMemoryLifecycleLedger`,
  `BM25Retriever`-shaped fakes, and the fixed `BM25Retriever` itself.

## Known limitations (not closed by this lot)

- **BM25 small-corpus IDF-floor gap** (found in Lot 4, `test_retrieve_returns_no_hits_for_a_relevant_document_in_a_too_small_corpus`)
  is unrelated to append/delete and remains open — explicitly owned by Lot 12b.
- **Index schema/versioning and vector/lexical divergence detection** are Lot 12b's job, not this
  one — this lot makes deletion *possible and coordinated*; Lot 12b is what *detects* the two
  sides silently drifting apart if a caller bypasses `RAGEngine` (e.g. calling
  `container.indexer.delete()` directly, still possible and still unmirrored — the same
  bypass-the-engine gap Lot 4 characterized, now only closed for callers that go through
  `RAGEngine.delete_document()`).
- **No manifest/registry wiring** for `lifecycle_ledger` — like every other optional component
  introduced this session, it's Container-registrable but not yet exposed as a manifest YAML
  option. Consistent with Lot 9's own precedent (introduce new capability, don't change default
  behavior as a side effect).

## Lot 12a acceptance (per `docs/refactoring-plan.md`, Lot 12a's own description)

"Define document identity, idempotent ingestion, update, deletion, and tombstone semantics" — all
five delivered and tested: identity (`document_key`), idempotency (skip-unchanged), update
(delete-old-then-index-new with version bump), deletion (`delete_document`, coordinated across
both index sides), tombstones (`DocumentStatus.TOMBSTONED`, idempotent re-deletion).

## Next

Lot 12b (index schema/reconciliation) — the largest sub-lot in Phase C per the plan's own sizing
note; consider a mid-lot checkpoint. Owns: index schema/version, atomic-or-reconcilable
vector/lexical writes, the reconciliation job for BM25/vector divergence, and the BM25
small-corpus IDF-floor fix flagged above.
