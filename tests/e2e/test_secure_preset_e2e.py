"""Deterministic e2e scenario for the secure-enterprise-rag.yaml governance
stack (tenant isolation, redaction, policy-as-code, durable audit) — Lot 4.

Requires a real Qdrant on localhost:6333 and a real PostgreSQL on
localhost:5432 (override via MRAG_TEST_QDRANT_URL / MRAG_TEST_POSTGRES_DSN,
same convention as tests/integration/test_qdrant_store.py and
tests/integration/test_postgres_audit_sink.py). No LLM API key of any kind —
`tests/e2e/manifests/secure-deterministic-rag.yaml` wires
`adapters.embeddings.deterministic_embedder.DeterministicEmbedder` and
`generation.synthesizers.deterministic_gen.DeterministicGenerator` instead of
sentence-transformers/OpenAI, so ingestion and generation both run with zero
network calls beyond Qdrant/PostgreSQL themselves.

Local reproduction:

    # 1. Start the two services (any equivalent local install works too):
    docker run -d -p 6333:6333 qdrant/qdrant
    docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16

    # 2. Run just this file:
    pytest tests/e2e/test_secure_preset_e2e.py -v -m e2e

    # 3. To point at non-default service locations:
    MRAG_TEST_QDRANT_URL=http://myhost:6333 \\
    MRAG_TEST_POSTGRES_DSN=postgresql://user:pass@myhost:5432/mydb \\
    pytest tests/e2e/test_secure_preset_e2e.py -v -m e2e

If either service is unreachable, every test in this module is skipped (not
failed) — see `_require_services` below.

Manual reproduction of a single answer(), without pytest and independent of
this module's own fixture lifecycle (Codex review, MED-002: a pytest
invocation's module-scoped fixture tears down — dropping the Qdrant
collection — as soon as that invocation finishes, so "run one pytest test,
then run the replay script separately" never actually worked; ingest through
the standalone script itself instead, in two steps):

    python tests/e2e/_secure_preset_replay.py \\
        --manifest tests/e2e/manifests/secure-deterministic-rag.yaml \\
        --ingest-fixtures

    python tests/e2e/_secure_preset_replay.py \\
        --manifest tests/e2e/manifests/secure-deterministic-rag.yaml \\
        --tenant-id e2e-tenant-a \\
        --question "What does the quarterly revenue report say about the whale-watching sector?"

See `_secure_preset_replay.py`'s own docstring for exact semantics
(`--ingest-fixtures` ingests the same `_secure_preset_fixtures.py` content
this module's own `app_and_chunks` fixture does — the two share that module
so they can't silently drift apart). This test module itself builds
`Document` objects directly in Python (not CLI file-based ingestion) for
tight control over content and tenant assignment.

Design notes worth reading before changing this file:

- Both tenants are ingested into ONE shared `ApplicationService`/Qdrant
  collection (matching how a real multi-tenant deployment actually works —
  tenant separation is a runtime policy over shared storage, not separate
  storage). Isolation is enforced by `TenantIsolationPolicy`
  (security/policies/tenant_isolation.py), not by physical separation.
- `HybridRetriever`'s BM25 half (retrieval/retrievers/bm25.py) has NO tenant
  awareness at all — only the vector half gets a server-side Qdrant payload
  filter (retrieval/retrievers/vector.py). The two tenants' documents share
  vocabulary ("quarterly revenue report... sector... Earth") on purpose, so
  BM25 genuinely cross-matches both tenants' content before
  `TenantIsolationPolicy.filter_chunks()` removes what doesn't belong —
  see `test_bm25_cross_match_is_filtered_out_by_tenant_policy`. Content that
  shared no vocabulary would make that assertion vacuously trivial.
- `RAGEngine` builds a `Trace` (with a `tenant_filter` before/after
  TraceStep) internally but does not return it — `NativeEngineAdapter.run()`
  documents this as a pre-existing gap ("RAGEngine builds a Trace internally
  but doesn't return it"). `ApplicationService.answer()` inherits that gap,
  so the before/after count is proven here by calling the wired retriever
  directly (bypassing tenant_policy) via `app._native.retriever` —
  `RAGEngine.retriever` is a public accessor; `ApplicationService._native` is
  not, but reaching through it for verification purposes matches this
  codebase's existing test convention of inspecting adapter internals
  directly (e.g. `tests/unit/orchestration/test_registry.py`).
- A "restart" is proven with a genuine separate OS process
  (`_secure_preset_replay.py` via `subprocess.run`), not a second
  same-process `ApplicationService` — a same-process rebuild cannot rule out
  in-process module-level state quietly carrying over (test-specialist
  review, Lot 4).
- `BM25Retriever` (retrieval/retrievers/bm25.py) is in-memory only; nothing
  in `wire()` reconciles it against Qdrant/`IndexReconciler` automatically
  on load. A fresh process therefore starts with an EMPTY lexical index —
  `HybridRetriever` degrades to vector-only, silently. This is real,
  documented, current behavior, not a bug this lot introduces or fixes —
  `test_bm25_index_is_empty_immediately_after_a_fresh_load` asserts it
  explicitly rather than letting the restart test pass for the wrong reason.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

from modular_rag.app.public import load_application
from modular_rag.core.errors import PolicyViolationError
from modular_rag.core.models.document import Document
from modular_rag.core.models.query import Query
from tests.e2e._secure_preset_fixtures import (
    TENANT_A,
    TENANT_A_CONTENT,
    TENANT_B,
    TENANT_B_CONTENT,
    render_manifest,
)

_HERE = Path(__file__).parent
REPLAY_SCRIPT = _HERE / "_secure_preset_replay.py"

QDRANT_URL = os.environ.get("MRAG_TEST_QDRANT_URL", "http://localhost:6333")
POSTGRES_DSN = os.environ.get(
    "MRAG_TEST_POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)
COLLECTION = "e2e_secure_deterministic"

QUESTION_A = "What does the quarterly revenue report say about the whale-watching sector?"
QUESTION_B = "What does the quarterly revenue report say about the mountain climbing sector?"
# No "export"/"hr-restricted" substring — see PolicyEngine's inline rules in
# the manifest; those two words are reserved for the dedicated denial tests
# below and must not appear in any other question by accident.
QUESTION_PII = (
    "Please send a summary of the whale-watching sector to alice@example.com."
)
QUESTION_EXPORT = "Please export this data for me."


def _host_port(url: str, default_port: int) -> tuple[str, int]:
    """Parse host/port out of a Qdrant HTTP URL or a PostgreSQL DSN — both
    are valid URIs, so `urlparse` handles either. Used so `_require_services`
    and `manifest_path` below probe/target wherever
    MRAG_TEST_QDRANT_URL/MRAG_TEST_POSTGRES_DSN actually point, not a
    hardcoded localhost (Codex review, MED-001)."""
    parsed = urlparse(url)
    return parsed.hostname or "localhost", parsed.port or default_port


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module", autouse=True)
def _require_services():
    qdrant_host, qdrant_port = _host_port(QDRANT_URL, 6333)
    postgres_host, postgres_port = _host_port(POSTGRES_DSN, 5432)
    if not _port_open(qdrant_host, qdrant_port):
        pytest.skip(f"Qdrant not reachable on {qdrant_host}:{qdrant_port} — not executed.")
    if not _port_open(postgres_host, postgres_port):
        pytest.skip(f"PostgreSQL not reachable on {postgres_host}:{postgres_port} — not executed.")


@pytest.fixture(scope="module")
def manifest_path(tmp_path_factory) -> Path:
    """Render the static e2e manifest template with the resolved (possibly
    env-overridden) Qdrant/PostgreSQL locations substituted in, so
    MRAG_TEST_QDRANT_URL/MRAG_TEST_POSTGRES_DSN genuinely reach
    `load_application()` and the restart subprocess — not just this module's
    own service-probe/cleanup code. Delegates to the shared
    `_secure_preset_fixtures.render_manifest()` helper — Codex review
    (second occurrence, MED-002): the *standalone* `_secure_preset_replay.py`
    script needs to resolve the exact same two environment variables the
    exact same way when run outside pytest, so the rendering logic itself
    cannot live only in this fixture."""
    return render_manifest(
        tmp_path_factory.mktemp("e2e-manifest"), qdrant_url=QDRANT_URL, postgres_dsn=POSTGRES_DSN
    )


def _drop_qdrant_collection_if_present() -> None:
    """A genuinely dimension-agnostic "drop if present" — Codex review,
    HIGH-001 (second occurrence): `QdrantStore.clear()` calls
    `_get_client()` first, and `_get_client()` itself validates an
    *existing* collection's dimension via `_ensure_collection()` before
    `clear()` ever reaches its own `delete_collection()` call. A stale
    collection left over at a mismatched dimension (from an older version of
    this fixture, a manual experiment, or any future dimension change) makes
    `_get_client()` raise `ConfigurationError` before deletion — so
    `QdrantStore.clear()` can never actually recover from that state, which
    is exactly the state a cleanup step exists to handle. A raw
    `qdrant_client.QdrantClient` bypasses that validation entirely: it only
    asks "does this name exist," never "is it the right shape" — matching
    what a cleanup step actually needs."""
    from qdrant_client import QdrantClient

    client = QdrantClient(url=QDRANT_URL)
    try:
        existing = [c.name for c in client.get_collections().collections]
        if COLLECTION in existing:
            client.delete_collection(collection_name=COLLECTION)
    finally:
        client.close()


def _pg_connection():
    import psycopg

    return psycopg.connect(POSTGRES_DSN, autocommit=True)


def _clean_audit_rows() -> None:
    # ADR-0011 (PostgreSQL migrations, connection pooling, and audit
    # retention): `PostgresAuditSink` no longer creates its schema
    # implicitly on connect — `auto_migrate=True` (documented as
    # local/dev-only convenience, never for production; see
    # docs/guides/postgres-permissions.md) runs the same migration files
    # `mrag db migrate` uses, so this helper stays safe to call before any
    # ingest/answer has ever run against a genuinely fresh PostgreSQL, same
    # as the retired implicit-DDL-on-first-connect behavior it replaces —
    # without a second, parallel schema mechanism. `_get_connection()`
    # (the method this used to call) no longer exists — `PostgresAuditSink`
    # exposes a `psycopg_pool.ConnectionPool` via `_get_pool()` now, not a
    # single cached connection.
    # One explicitly-closed sink/pool for both the migration side effect and the
    # DELETE, instead of a temporary sink whose connection was silently abandoned
    # (no close() existed to call) plus a second, separate _pg_connection() for the
    # delete itself (Codex review, MED-003 — PostgresAuditSink now has a real close()).
    from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink

    sink = PostgresAuditSink(dsn=POSTGRES_DSN, auto_migrate=True)
    try:
        with sink._get_pool().connection() as conn:
            conn.execute(
                "DELETE FROM audit_events WHERE tenant_id IN (%s, %s, 'unknown')",
                (TENANT_A, TENANT_B),
            )
    finally:
        sink.close()


def _fetch_audit_rows(tenant_id: str, event_type: str | None = None) -> list[tuple]:
    with _pg_connection() as conn:
        if event_type is None:
            return conn.execute(
                "SELECT event_type, tenant_id, payload FROM audit_events "
                "WHERE tenant_id = %s ORDER BY timestamp",
                (tenant_id,),
            ).fetchall()
        return conn.execute(
            "SELECT event_type, tenant_id, payload FROM audit_events "
            "WHERE tenant_id = %s AND event_type = %s ORDER BY timestamp",
            (tenant_id, event_type),
        ).fetchall()


@pytest.fixture(scope="module")
def app_and_chunks(manifest_path):
    """Ingest both tenants once per module run; individual tests only query
    (test-specialist review, Lot 4)."""
    _drop_qdrant_collection_if_present()
    _clean_audit_rows()

    application = load_application(str(manifest_path))

    doc_a = Document(source="tenant-a-quarterly-report.txt", content=TENANT_A_CONTENT, tenant_id=TENANT_A)
    doc_b = Document(source="tenant-b-quarterly-report.txt", content=TENANT_B_CONTENT, tenant_id=TENANT_B)
    chunks_a = application.chunker.chunk(doc_a)
    chunks_b = application.chunker.chunk(doc_b)
    assert chunks_a and chunks_b, "chunker produced no chunks — check TENANT_*_CONTENT/chunk_size"
    application.ingest_chunks(chunks_a)
    application.ingest_chunks(chunks_b)

    yield application, {c.id for c in chunks_a}, {c.id for c in chunks_b}

    application.close()
    _drop_qdrant_collection_if_present()
    _clean_audit_rows()


@pytest.mark.e2e
def test_no_external_llm_key_required(app_and_chunks, monkeypatch):
    """The literal "aucune clé externe obligatoire" acceptance criterion,
    proven live rather than assumed from the manifest's component types."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    application, chunk_ids_a, _ = app_and_chunks

    answer = application.answer(QUESTION_A, tenant_id=TENANT_A)

    assert answer.text
    assert {c.chunk_id for c in answer.citations} <= chunk_ids_a


@pytest.mark.e2e
def test_tenant_a_receives_only_its_own_citations(app_and_chunks):
    application, chunk_ids_a, chunk_ids_b = app_and_chunks

    answer = application.answer(QUESTION_A, tenant_id=TENANT_A)

    cited = {c.chunk_id for c in answer.citations}
    assert cited, "expected at least one citation"
    assert cited <= chunk_ids_a
    assert not (cited & chunk_ids_b)


@pytest.mark.e2e
def test_tenant_b_receives_only_its_own_citations(app_and_chunks):
    application, chunk_ids_a, chunk_ids_b = app_and_chunks

    answer = application.answer(QUESTION_B, tenant_id=TENANT_B)

    cited = {c.chunk_id for c in answer.citations}
    assert cited, "expected at least one citation"
    assert cited <= chunk_ids_b
    assert not (cited & chunk_ids_a)


@pytest.mark.e2e
def test_bm25_cross_match_is_filtered_out_by_tenant_policy(app_and_chunks):
    """The isolation mechanism itself, not just its outcome (security-specialist
    review, Lot 4): prove the BM25 half of HybridRetriever genuinely surfaces
    tenant-b's chunk for tenant-a's query (shared vocabulary, no tenant
    awareness in BM25Retriever), and that TenantIsolationPolicy.filter_chunks()
    is what removes it — not that it was simply never retrieved."""
    application, chunk_ids_a, chunk_ids_b = app_and_chunks

    raw_query = Query(text=QUESTION_A, tenant_id=TENANT_A)
    raw_hits = application._native.retriever.retrieve(raw_query, k=20)
    raw_ids = {rc.chunk.id for rc in raw_hits}

    filtered_result = application.retrieve(QUESTION_A, k=20, tenant_id=TENANT_A)
    filtered_ids = {rc.chunk.id for rc in filtered_result.chunks}

    assert raw_ids & chunk_ids_b, (
        "expected BM25's lexical overlap to surface at least one tenant-b chunk "
        "before filtering — if this fails, TENANT_A_CONTENT/TENANT_B_CONTENT no "
        "longer share enough vocabulary to exercise this path"
    )
    assert not (filtered_ids & chunk_ids_b)
    assert filtered_ids <= chunk_ids_a


@pytest.mark.e2e
def test_cross_tenant_retrieve_call_excludes_other_tenant(app_and_chunks):
    """tenant-b explicitly asking about tenant-a's topic — impossibilité
    d'accès croisé, via the raw retrieve() path (no generation)."""
    application, chunk_ids_a, _ = app_and_chunks

    result = application.retrieve(QUESTION_A, k=20, tenant_id=TENANT_B)

    assert not ({rc.chunk.id for rc in result.chunks} & chunk_ids_a)


@pytest.mark.e2e
def test_query_without_tenant_id_is_denied(app_and_chunks):
    """Fail-closed: no identity at all must deny outright, not degrade to an
    unscoped/empty answer. Also records two distinct audit rows for the
    denial (engine.py: the tenant-check except block writes a GUARD_DECISION,
    then _run()'s outer except writes RUN_FAILED for the same re-raised
    exception) — both under tenant_id='unknown' (`query.tenant_id or
    "unknown"`), never NULL (security-specialist review, Lot 4)."""
    application, _, _ = app_and_chunks
    _clean_audit_rows()

    with pytest.raises(PolicyViolationError):
        application.answer(QUESTION_A, tenant_id=None)

    rows = _fetch_audit_rows("unknown")
    event_types = [r[0] for r in rows]
    assert "guard_decision" in event_types
    assert "run_failed" in event_types


@pytest.mark.e2e
def test_ingest_without_tenant_id_is_denied(app_and_chunks):
    """The ingest-time half of fail-closed tenant isolation
    (TenantIsolationPolicy.enforce_ingest) — a chunk with no tenant_id must
    never reach the index at all, not merely get filtered out later at query
    time (which would also make it silently indistinguishable from a filter
    bug, per security-specialist review)."""
    application, _, _ = app_and_chunks
    orphan_doc = Document(source="orphan.txt", content="unaffiliated content", tenant_id=None)
    orphan_chunks = application.chunker.chunk(orphan_doc)

    with pytest.raises(PolicyViolationError):
        application.ingest_chunks(orphan_chunks)


@pytest.mark.e2e
def test_policy_engine_denies_export_query(app_and_chunks):
    """Exercises the wired policy_engine's inline rules directly (not just
    tenant isolation) — otherwise this governance component is wired but
    never actually verified by this scenario (test-specialist review, Lot 4)."""
    application, _, _ = app_and_chunks

    with pytest.raises(PolicyViolationError, match="export"):
        application.answer(QUESTION_EXPORT, tenant_id=TENANT_A)


@pytest.mark.e2e
def test_pii_query_is_redacted_in_audit_trail(app_and_chunks):
    """The query itself carries PII (an email) — the chunk content never
    does, so the answer text (which quotes chunk content) is unaffected by
    redaction and stays assertable; only the audit payload's
    query_text_redacted field is checked here."""
    application, _, _ = app_and_chunks
    _clean_audit_rows()

    answer = application.answer(QUESTION_PII, tenant_id=TENANT_A)
    assert answer.text  # succeeds normally — PII in the query doesn't block it

    rows = _fetch_audit_rows(TENANT_A, event_type="run_succeeded")
    assert rows, "expected a run_succeeded audit row for this query"
    payload = rows[-1][2]
    redacted = payload["query_text_redacted"]
    assert "[REDACTED]" in redacted
    assert "alice@example.com" not in redacted


@pytest.mark.e2e
def test_generation_is_deterministic_across_repeated_calls(app_and_chunks):
    application, _, _ = app_and_chunks

    first = application.answer(QUESTION_A, tenant_id=TENANT_A)
    second = application.answer(QUESTION_A, tenant_id=TENANT_A)

    assert first.text == second.text
    assert [c.chunk_id for c in first.citations] == [c.chunk_id for c in second.citations]


@pytest.mark.e2e
def test_audit_trail_records_successful_runs_per_tenant(app_and_chunks):
    application, _, _ = app_and_chunks
    _clean_audit_rows()

    application.answer(QUESTION_A, tenant_id=TENANT_A)
    application.answer(QUESTION_B, tenant_id=TENANT_B)

    rows_a = _fetch_audit_rows(TENANT_A, event_type="run_succeeded")
    rows_b = _fetch_audit_rows(TENANT_B, event_type="run_succeeded")
    assert rows_a and all(r[1] == TENANT_A for r in rows_a)
    assert rows_b and all(r[1] == TENANT_B for r in rows_b)


@pytest.mark.e2e
def test_bm25_index_is_empty_immediately_after_a_fresh_load(app_and_chunks, manifest_path):
    """Documents the real, current gap this module's docstring describes:
    BM25Retriever is in-memory only and nothing reconciles it against Qdrant
    on load. A same-process fresh ApplicationService — not the subprocess
    restart below — is enough to check this directly."""
    _application, _, _ = app_and_chunks  # ensures ingestion already happened

    fresh = load_application(str(manifest_path))
    try:
        bm25_ids = fresh._native.retriever._bm25.list_ids()
        assert bm25_ids == []
    finally:
        fresh.close()


@pytest.mark.e2e
def test_citations_survive_a_genuine_process_restart(app_and_chunks, manifest_path):
    """The literal "redémarrer l'application et rejouer les requêtes"
    acceptance criterion, via a real separate OS process (see this module's
    docstring for why a same-process rebuild wouldn't prove this). Compares
    citation chunk_id sets, not full answer text/score — vector-only
    retrieval after "restart" (see the BM25-empty test above) can reorder
    equally-scored hits differently than the hybrid-fused pre-restart run."""
    application, chunk_ids_a, _ = app_and_chunks
    before = application.answer(QUESTION_A, tenant_id=TENANT_A)
    before_ids = {c.chunk_id for c in before.citations}
    assert before_ids, "expected at least one citation before restart"

    result = subprocess.run(
        [
            sys.executable,
            str(REPLAY_SCRIPT),
            "--manifest",
            str(manifest_path),
            "--tenant-id",
            TENANT_A,
            "--question",
            QUESTION_A,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    replayed = json.loads(result.stdout)
    after_ids = {c["chunk_id"] for c in replayed["citations"]}

    assert after_ids, "expected at least one citation after restart"
    assert after_ids == before_ids
    assert after_ids <= chunk_ids_a
