"""Unit tests for ingestion/pipelines/default.py (ingest_path/ingest_directory).

Tenant-aware ingestion, a follow-up to the tenant fail-closed fix on `ask`:
`--tenant-id` on `mrag ingest` is useless unless the tenant it names actually
reaches every `Chunk` produced from disk. Before this lot, no parser ever set
`Document.tenant_id`, and neither pipeline function had a parameter to inject
one — every chunk from the file-ingestion path had `tenant_id=None`
regardless of caller intent, which `RAGEngine.ingest_chunks()`'s fail-closed
`enforce_ingest()` check then unconditionally rejected against any
tenant-isolated manifest.

Uses a fake `Chunker` that mirrors the real chunkers' own tenant propagation
(`document.tenant_id` copied onto each `Chunk`, confirmed already correct in
`ingestion/chunkers/fixed.py`/`adaptive.py`) so these tests isolate exactly
what `ingest_path`/`ingest_directory` are responsible for: getting the right
`tenant_id` onto the `Document` they hand to the chunker in the first place.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.document import Document
from modular_rag.ingestion.pipelines.default import (
    _apply_tenant_id,
    ingest_directory,
    ingest_path,
)


class _FakeChunker:
    """One chunk per document, tenant_id copied straight across — matches
    every real Chunker implementation's own propagation."""

    def chunk(self, document: Document) -> list[Chunk]:
        return [Chunk(doc_id=document.id, content=document.content, tenant_id=document.tenant_id)]

    def name(self) -> str:
        return "fake-chunker"


def _write(tmp_path: Path, name: str, content: str = "hello world") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_ingest_path_propagates_tenant_id_to_every_chunk(tmp_path: Path) -> None:
    doc_file = _write(tmp_path, "doc.txt")

    chunks = ingest_path(doc_file, _FakeChunker(), tenant_id="acme-corp")

    assert len(chunks) == 1
    assert chunks[0].tenant_id == "acme-corp"


def test_ingest_path_without_a_tenant_id_yields_none(tmp_path: Path) -> None:
    """Backward compatibility: an unsecured/local manifest never passes
    --tenant-id, and ingestion must behave exactly as it did before this
    lot — no tenant fabricated, no crash."""
    doc_file = _write(tmp_path, "doc.txt")

    chunks = ingest_path(doc_file, _FakeChunker())

    assert len(chunks) == 1
    assert chunks[0].tenant_id is None


def test_ingest_directory_propagates_tenant_id_across_every_file(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", "first document")
    _write(tmp_path, "b.txt", "second document")

    chunks = ingest_directory(tmp_path, _FakeChunker(), tenant_id="acme-corp")

    assert len(chunks) == 2
    assert all(c.tenant_id == "acme-corp" for c in chunks)


def test_ingest_directory_without_a_tenant_id_yields_none_for_every_chunk(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "a.txt", "first document")
    _write(tmp_path, "b.txt", "second document")

    chunks = ingest_directory(tmp_path, _FakeChunker())

    assert len(chunks) == 2
    assert all(c.tenant_id is None for c in chunks)


def test_unsupported_file_type_is_skipped_without_error_or_a_leaked_tenant(
    tmp_path: Path,
) -> None:
    unsupported = tmp_path / "archive.zip"
    unsupported.write_bytes(b"not a real zip, just unsupported bytes")

    chunks = ingest_path(unsupported, _FakeChunker(), tenant_id="acme-corp")

    assert chunks == []


def test_ingest_directory_mixed_supported_and_unsupported_files(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", "supported")
    (tmp_path / "b.zip").write_bytes(b"unsupported")

    chunks = ingest_directory(tmp_path, _FakeChunker(), tenant_id="acme-corp")

    assert len(chunks) == 1
    assert chunks[0].tenant_id == "acme-corp"


# ---------------------------------------------------------------------------
# Acceptance criterion: "empêcher qu'un tenant fourni dans les métadonnées
# documentaires écrase silencieusement l'identité explicite." No parser sets
# Document.tenant_id from source metadata today (confirmed: ingestion-specialist
# review), so this is exercised directly against the override helper rather
# than through a real parser — the guarantee that matters is that an explicit
# tenant_id always wins over whatever a Document already carries, from
# whatever source, not just over the current "always None" reality.
# ---------------------------------------------------------------------------


def test_apply_tenant_id_overrides_any_preexisting_tenant_id() -> None:
    doc = Document(source="x.txt", content="hi", tenant_id="metadata-derived-tenant")

    result = _apply_tenant_id(doc, "explicit-tenant")

    assert result.tenant_id == "explicit-tenant"


def test_apply_tenant_id_leaves_the_document_unchanged_when_not_provided() -> None:
    """No --tenant-id given: the document's own tenant_id (whatever it is)
    is left alone, not reset to None."""
    doc = Document(source="x.txt", content="hi", tenant_id="already-set")

    result = _apply_tenant_id(doc, None)

    assert result.tenant_id == "already-set"


# ---------------------------------------------------------------------------
# End-to-end (in-memory, no external services): the real ingest_path() +
# real FixedSizeChunker + real RAGEngine + real TenantIsolationPolicy chained
# together — test-specialist review found each link individually tested but
# never the full chain, which is what actually matters for `mrag ingest`.
# ---------------------------------------------------------------------------


def _tenant_engine():  # type: ignore[no-untyped-def]
    from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
    from modular_rag.orchestration.container import Container
    from modular_rag.orchestration.engine import RAGEngine
    from modular_rag.security.policies.tenant_isolation import TenantIsolationPolicy

    class _FakeEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

        def name(self) -> str:
            return "fake-embedder"

    class _FakeIndexer:
        def __init__(self) -> None:
            self.indexed: list[Chunk] = []

        def index(self, chunks: list[Chunk]) -> None:
            self.indexed.extend(chunks)

    manifest = PipelineManifest(
        id="ingest-e2e-test",
        chunker=ComponentConfig(type="fake"),
        embedder=ComponentConfig(type="fake"),
        indexer=ComponentConfig(type="fake"),
        retriever=ComponentConfig(type="fake"),
        generator=ComponentConfig(type="fake"),
    )
    container = Container(manifest)
    container.register("chunker", object())
    container.register("embedder", _FakeEmbedder())
    container.register("indexer", _FakeIndexer())
    container.register("retriever", object())
    container.register("generator", object())
    container.register("tenant_policy", TenantIsolationPolicy())
    return RAGEngine(container), container


def test_end_to_end_ingest_path_with_tenant_succeeds_through_a_real_engine(
    tmp_path: Path,
) -> None:
    from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker

    doc_file = _write(tmp_path, "doc.txt", "hello world, this is a real document")
    engine, container = _tenant_engine()

    chunks = ingest_path(doc_file, FixedSizeChunker(), tenant_id="acme-corp")
    n = engine.ingest_chunks(chunks)

    assert n == len(chunks) > 0
    assert all(c.tenant_id == "acme-corp" for c in container.indexer.indexed)


def test_end_to_end_ingest_path_without_tenant_is_denied_before_indexing(
    tmp_path: Path,
) -> None:
    from modular_rag.core.errors import PolicyViolationError
    from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker

    doc_file = _write(tmp_path, "doc.txt", "hello world, this is a real document")
    engine, container = _tenant_engine()

    chunks = ingest_path(doc_file, FixedSizeChunker())  # no tenant_id

    with pytest.raises(PolicyViolationError, match="tenant_id"):
        engine.ingest_chunks(chunks)
    assert container.indexer.indexed == []
