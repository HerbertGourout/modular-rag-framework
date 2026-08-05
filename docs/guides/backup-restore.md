# Backup, Restore, and Rollback

Lot 16c (`docs/refactoring-plan.md`) — the runbook Lots 12c and 14 deferred here explicitly:
Lot 12c proved the lifecycle-ledger backup/restore *mechanism* with a genuine round-trip
exercise but left production PostgreSQL/Qdrant-native tooling "documented, not reimplemented";
Lot 14 left overload/soak evidence for this lot, "needs live load-testing infra." Both are
addressed below with real, runnable commands. **Honesty note, read before relying on this
document**: none of the Postgres/Qdrant/container commands below were executed against live
infrastructure while writing this — the sandboxed environment this lot was written in has no
`docker`, `psql`, `pg_dump`, or reachable Qdrant/Postgres instance (verified: `which docker
psql pg_dump` all fail, `curl localhost:6333` and `localhost:5432` both refuse to connect). Every
command is either (a) this framework's own tested Python-level API, or (b) Postgres'/Qdrant's own
standard, publicly documented tooling used exactly as documented upstream — not invented syntax —
but "documented correctly" is not the same claim as "executed here." The first time any team runs
these for real, treat it as the actual verification exercise, and record what happened.

---

## What backs up what

| Component | What it holds | Backup mechanism | Owned by |
|---|---|---|---|
| Lifecycle ledger | Document identity, content hash, chunk ids, status (ingested/tombstoned) — **never chunk content** | `ingestion/lifecycle/backup.py`'s `backup_ledger()`/`restore_ledger()` (portable JSON, any `LifecycleLedger` implementation) **or** Postgres-native `pg_dump`/`pg_restore` on the `document_lifecycle` table, if using `PostgresLifecycleLedger` | This framework (JSON path) / PostgreSQL (native path) |
| Audit trail | Compliance evidence (`AuditEvent`s) — append-only | Postgres-native `pg_dump`/`pg_restore` on the `audit_events` table, if using `PostgresAuditSink` | PostgreSQL |
| Vector index | Chunk embeddings + payload (including `tenant_id`, Lot 12b) | Qdrant-native snapshot API | Qdrant |
| Lexical index (BM25) | In-memory only, rebuilt from ingestion — **not backed up** | Re-`ingest()` from source, or `rebuild_document()` | This framework |
| Source documents | The actual content everything else derives from | Whatever your own document store/object storage already does — out of this framework's scope | You |

The one fact every procedure below depends on: **losing the ledger or the vector index is
recoverable from source documents via `RAGEngine.rebuild_document()`** (Lot 12c) as long as
source documents themselves are intact. Losing source documents is not recoverable by anything
in this framework.

---

## Lifecycle ledger

### Portable JSON backup (any `LifecycleLedger` — in-memory or Postgres)

```python
from modular_rag.ingestion.lifecycle.backup import backup_ledger, restore_ledger

# Backup
snapshot = backup_ledger(container.lifecycle_ledger)
Path("ledger-backup.json").write_text(snapshot, encoding="utf-8")

# Restore (into the same or a fresh ledger instance)
restore_ledger(container.lifecycle_ledger, Path("ledger-backup.json").read_text(encoding="utf-8"))
```

**Proven** (`tests/unit/ingestion/lifecycle/test_backup.py`, Lot 12c): a genuine fresh-instance
round trip — records backed up from one `InMemoryLifecycleLedger`, restored into a brand-new
instance, verified identical including tombstoned records (a backup that silently dropped
tombstone history would make right-to-erasure proof unverifiable after a restore). This
mechanism is ledger-implementation-agnostic — it only calls `LifecycleLedger.export_all()`/
`restore_record()` (`contracts/lifecycle.py`), so it works identically against
`PostgresLifecycleLedger`. **Not separately proven against a live Postgres instance in this
lot** — `tests/integration/test_postgres_lifecycle_ledger.py` covers the Postgres adapter's own
CRUD correctness but requires live Postgres to run, which this sandboxed environment does not
have.

### Postgres-native backup (`PostgresLifecycleLedger`, disaster-recovery grade)

```bash
# Backup the document_lifecycle table (adapters/lifecycle/postgres_ledger.py)
pg_dump --table=document_lifecycle --data-only --format=custom \
        --file=document_lifecycle.dump "$MRAG_POSTGRES_DSN"

# Restore into a fresh or recovered database
pg_restore --table=document_lifecycle --data-only \
           --dbname="$MRAG_POSTGRES_DSN" document_lifecycle.dump
```

Use this over the JSON path for disaster recovery at scale (point-in-time recovery, WAL
archiving, standard Postgres operational tooling) — the JSON path is for portable,
implementation-agnostic snapshots (moving state out of `InMemoryLifecycleLedger`, a lightweight
manual export), not a replacement for `pg_dump` in production.

---

## Audit trail (`PostgresAuditSink`)

```bash
# Backup the audit_events table (adapters/audit/postgres_sink.py) — append-only,
# so a --data-only dump is always consistent with "everything up to now."
pg_dump --table=audit_events --data-only --format=custom \
        --file=audit_events.dump "$MRAG_POSTGRES_DSN"

# Restore
pg_restore --table=audit_events --data-only \
           --dbname="$MRAG_POSTGRES_DSN" audit_events.dump
```

Audit evidence has its own retention/residency requirements (recorded as open in
`docs/refactoring-plan.md` §10, owners Lot 16c/11c) — this is the mechanical backup procedure,
not a retention policy. Decide retention duration separately before relying on this alone for
compliance.

---

## Vector index (Qdrant)

This framework does not wrap Qdrant's own snapshot API (`orchestration/reconciliation.py`'s
`IndexReconciler` repairs *divergence* between the ledger and the index — orphaned ids only,
never fabricates missing content — it is not a backup tool). Use Qdrant's native snapshot
mechanism directly, against the collection name your manifest configures
(`indexer.config.collection`, default `mrag_default` — `adapters/vectorstores/qdrant_store.py`):

```bash
# Create a snapshot
curl -X POST "http://localhost:6333/collections/mrag_default/snapshots"

# List snapshots
curl "http://localhost:6333/collections/mrag_default/snapshots"

# Download a snapshot (SNAPSHOT_NAME from the list above)
curl -o mrag_default.snapshot \
     "http://localhost:6333/collections/mrag_default/snapshots/SNAPSHOT_NAME"

# Restore into a (new or the same) collection
curl -X PUT "http://localhost:6333/collections/mrag_default/snapshots/upload" \
     -H "Content-Type: multipart/form-data" \
     -F "snapshot=@mrag_default.snapshot"
```

After a vector-index restore, run `IndexReconciler.check()` (Lot 12b,
`orchestration/reconciliation.py`) against the restored collection and the lifecycle ledger to
detect drift introduced by the snapshot's point-in-time gap (documents ingested after the
snapshot but before the incident), then `rebuild_document()` (Lot 12c) for anything the
reconciler flags as `unresolved_missing`.

---

## Rollback

Three independent rollback surfaces exist in this framework — pick the one that matches what
actually broke:

### Container image rollback

The `Dockerfile` (Lot 16b) produces an immutable image per build. Tag every build with an
identifying reference (a commit SHA, a semantic version) and roll back by re-running the
previous tag — never by patching a running container:

```bash
docker build -t modular-rag:<new-tag> .
docker run -d --name mrag-api -p 8000:8000 \
    -e MRAG_MANIFEST_PATH=manifests/presets/local-hybrid-rag.yaml \
    modular-rag:<new-tag>

# Roll back
docker stop mrag-api && docker rm mrag-api
docker run -d --name mrag-api -p 8000:8000 \
    -e MRAG_MANIFEST_PATH=manifests/presets/local-hybrid-rag.yaml \
    modular-rag:<previous-tag>
```

### Manifest schema rollback

Already proven (Lot 9): a v2 manifest can be migrated from v1 and the migration is exact —
`app/config_resolution.py`'s `migrate_v1_to_v2()` round-trips against the real runnable
manifest. Rolling back a manifest change is switching back to the previous file/git revision; no
in-place mutation makes this harder than a normal config change.

### Engine adapter rollback

Already proven (Lot 8, extended Lot 15): `manifest.engine.adapter: "native"` (the default) vs.
`"langgraph"` is a single YAML field. Rolling back from the LangGraph adapter to native is
changing that one field back — both wrap the identical wired `Container`, so no data migration
is involved, only which orchestration engine executes a request.

---

## Overload / soak evidence (deferred from Lot 14)

Lot 14 built timeouts, retry/circuit-breaker primitives, and thread-safety locks, but explicitly
left "overload/backpressure semantics (need live load-testing infra)" for this lot.
[`scripts/loadtest_answer.py`](../../scripts/loadtest_answer.py) is a real, runnable load-test
script — it was **not executed** in this sandboxed environment (no reachable deployment target).
Run it against a real deployment (the container from Lot 16b, or `uvicorn server:app` directly)
and record the actual results as this section's evidence — this document intentionally does not
fabricate numbers it cannot produce:

```bash
python scripts/loadtest_answer.py --url http://localhost:8000 --concurrency 20 --requests 200
```

What to look for once this is actually run: a 429 rate should climb as `--concurrency` exceeds
`create_app()`'s configured `rate_limit_per_minute` (Lot 16a) — that is the rate limiter working
as designed, not a failure. A genuine failure signature is 5xx responses or latency growing
without bound as concurrency increases; either means the deployment's worker count, timeout
settings (Lot 14's per-adapter `timeout` params), or `rate_limit_per_minute` need tuning before
this is production-ready at that load.
