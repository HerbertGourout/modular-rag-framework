# Lot 16c — Deployment, Backup, Restore, and Rollback Runbooks

**Date:** 2026-08-05
**Status:** COMPLETE (documentation/tooling scope) — execution evidence pending real infrastructure

## Scope (from `docs/refactoring-plan.md` §5, Phase D)

> Deployment, backup, restore, and rollback runbooks. Needs both 16a (what to deploy) and 16b
> (how it's built/scanned) finished first.

Acceptance bar (§6): "Deploy, backup, restore, and rollback commands are each executed at least
once, not just documented." **This lot does not fully meet that bar** — see "What could not be
verified" below. This is an infra-gated lot per the standing execution instruction ("lots needing
real infrastructure not available in this sandboxed environment: build code/contracts with
verifiable fakes, note what needs real infra"): confirmed directly before starting —
`which docker psql pg_dump` all fail, and `curl localhost:6333`/`localhost:5432` both refuse to
connect in this environment.

## What was built

| File | Purpose |
|---|---|
| `docs/guides/backup-restore.md` (new) | Real procedures for the lifecycle ledger (portable JSON via `backup_ledger()`/`restore_ledger()`, proven Lot 12c; plus Postgres-native `pg_dump`/`pg_restore` on `document_lifecycle`), the audit trail (`pg_dump`/`pg_restore` on `audit_events`), the vector index (Qdrant's own snapshot HTTP API against the manifest's configured collection), and three independent rollback surfaces (container image tag, manifest revision, `engine.adapter` field). Opens with an explicit honesty note about what was and wasn't executed. |
| `scripts/loadtest_answer.py` (new) | A real, runnable concurrent load-test script for `POST /answer` (`ThreadPoolExecutor`, configurable concurrency/request count, reports status-code distribution and p50/p95/max latency) — the overload/backpressure evidence Lot 14 deferred here. |
| `docs/guides/deployment.md` | Corrected in place — see "Findings while writing this" below. |
| `docs/refactoring-plan.md` | Gap-matrix rows updated (Resilience/overload, Index migration/Postgres-Qdrant backup, new "Orphaned `Settings` class" row, two §10 open-question rows corrected), acceptance-criteria row for Lot 16c annotated with what remains unmet. |

## Findings while writing this

Writing an accurate runbook required verifying every claim in the pre-existing
`docs/guides/deployment.md` against the actual code, not just against what the earlier draft
said. Several were wrong:

1. **`secure-enterprise-rag.yaml` was presented as a usable production manifest.** It's
   classified `BLUEPRINT`, not `RUNNABLE`, in `manifests/README.md` (Lot 5) — `wire()` never
   reads its `policies:` field, which also points at two files that don't exist. This slipped
   past Lot 5's own capability-truth audit (which covered README.md, `docs/api/rest.md`, and
   `docs/business-case.md`, not this file). Corrected to point at `local-hybrid-rag.yaml`, the
   only preset proven to wire end-to-end.
2. **The most material finding: `app/settings.py`'s entire `Settings` class is orphaned.**
   `MRAG_OPENAI_API_KEY`, `MRAG_QDRANT_URL`, `MRAG_QDRANT_API_KEY`, `MRAG_LOG_LEVEL`, and every
   other `Settings` field are declared but never read — `get_settings()`/`Settings()` is not
   called anywhere in `orchestration/_default_factories.py` or the pipeline-loading path.
   Verified with `grep -rn "Settings()" src/modular_rag/` (zero hits outside `settings.py`
   itself) and by reading every adapter factory (`AdapterClass(**cfg.config)` — sourced only
   from the manifest, never from environment). The one env var that *does* work is the OpenAI
   SDK's own standard `OPENAI_API_KEY` (not `MRAG_`-prefixed), because `OpenAIGenerator` passes
   `api_key=self.api_key or None` and the SDK falls through to its own lookup on `None`. Qdrant
   has no equivalent fallback at all — `url`/`api_key` must be explicit manifest literals.
   `docs/guides/deployment.md`'s previous version confidently documented `MRAG_OPENAI_API_KEY`
   and `MRAG_QDRANT_URL` as working — both false. Corrected throughout, and recorded as a new
   gap-matrix row ("Orphaned `Settings` class") rather than silently fixed, since wiring
   `Settings` into the factories is a real architectural decision (how does it interact with
   Lot 9's `resolve_manifest()`/`secret://` mechanism, which already exists as *a* answer to
   "how do secrets get into a manifest"?) outside this lot's "write a runbook" scope.
3. **The docker-compose example's Qdrant URL would silently fail.** `local-hybrid-rag.yaml`
   hardcodes `indexer.config.url: "http://localhost:6333"` — inside a compose network that
   resolves to the app container itself, not the `qdrant` service. Combined with finding #2
   (no env-var override exists), the example as originally written would connect-refuse against
   the wrong host with no way to fix it via environment variables. Documented explicitly rather
   than left as a trap.

None of these were touched or introduced by this lot's own prior work (Lots 15/16a/16b) — they
predate this session's changes to `docs/guides/deployment.md` and were only caught because this
lot required tracing every claim back to source before writing a runbook that depends on them
being true.

## What could not be verified

The acceptance bar for this lot is execution evidence, not documentation correctness. In this
sandboxed environment:

- No `docker` binary — the `Dockerfile` (Lot 16b) has never been built or run here. The new CI
  `container-build` job (`.github/workflows/ci.yml`, Lot 16b) is where this is actually executed,
  on GitHub Actions' runners, which do have Docker — that job's result on the next push is the
  real verification, not anything claimed in this document.
- No `psql`/`pg_dump`/reachable Postgres — the `pg_dump`/`pg_restore` commands in
  `docs/guides/backup-restore.md` are standard, correctly-used Postgres tooling (verified against
  Postgres' own documented flag syntax) against this framework's actual table names
  (`document_lifecycle`, `audit_events` — read directly from `adapters/lifecycle/postgres_ledger.py`
  and `adapters/audit/postgres_sink.py`'s `CREATE TABLE` statements), but never run.
- No reachable Qdrant — same status for the snapshot API commands (verified against Qdrant's own
  published REST API, using this framework's actual default collection name `mrag_default` from
  `adapters/vectorstores/qdrant_store.py`).
- No live deployment target — `scripts/loadtest_answer.py` was written and syntax/lint-checked
  (`ruff check`, `python -m py_compile`) but never run against a real server.

This is the same "verifiable fakes / defer to real infra" pattern used for PostgreSQL and
Keycloak in earlier lots, applied here to commands that have no meaningful local fake — only a
real Postgres/Qdrant/Docker daemon can prove "does this backup actually restore." The honest
status is: **written correctly, not yet proven.** The first team to run any of these for real
should treat that run as the actual verification exercise this lot's acceptance bar asks for, and
record what happened (a follow-up to this document, not a reason to distrust it — the commands
were verified against each system's real documented behavior, not invented).

## Deliberately out of scope, recorded honestly

- Audit-retention *enforcement* (a scheduled deletion job, DB-permission-level immutability) —
  `docs/refactoring-plan.md` §10 previously bundled this into "Lot 16c" implicitly; this lot did
  not build it (backup/restore/rollback and overload tooling only). Corrected in the tracker
  rather than silently left conflated.
  **Addendum (2026-08-18):** subsequently built via
  [ADR-0011](../adr/0011-postgresql-migrations-pooling-and-retention.md) — a separate track, not a
  return to this lot — see `docs/guides/postgres-permissions.md` and
  `PostgresAuditSink.purge_expired()`. Residency/legal/WORM immutability remain open; this
  addendum does not retroactively claim this lot addressed those.
- Target deployment platform/topology (cloud provider, Kubernetes vs. plain Docker, specific
  autoscaling policy) was never decided in this programme (`docs/refactoring-plan.md` §10 lists
  it as an open question "Before Lot 16c," never actually resolved). This lot built a
  platform-agnostic baseline (any container runtime can run the `Dockerfile`) precisely because
  no specific platform was chosen — not a gap this lot could close on its own authority.
- The orphaned `Settings` class (finding #2 above) is recorded as a new gap-matrix row, not fixed.

## Verification

`./scripts/check.sh full` — all 7 steps pass (mypy baseline unaffected, 31/31; 465 unit + 82
contract tests unaffected — this lot added one new Python file, `scripts/loadtest_answer.py`,
which is outside `src/modular_rag/`'s test-covered surface, manually verified via `ruff check`
and `python -m py_compile` instead).

## Tracker updates

- Header status block: Lot 16c → COMPLETE (documentation/tooling scope), execution pending real
  infra.
- Gap matrix: "Resilience" row updated (script exists, execution still open — not fully
  resolved). "Index migration" row's Lot 16c reference updated to reflect the runbook now
  existing, with the same execution caveat. New "Orphaned `Settings` class" row.
- §10 open questions: "Target deployment platform and topology" and "Audit retention
  enforcement" rows corrected to reflect what this lot actually did and didn't resolve.
- Acceptance-criteria table: Lot 16c row annotated with what remains unmet and why.
- Decision log + change history: new Lot 16c entry.
