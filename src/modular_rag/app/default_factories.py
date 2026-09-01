"""Application composition for the built-in component catalogue."""
from __future__ import annotations

from typing import TYPE_CHECKING

from modular_rag.orchestration.registry import ComponentRegistry

if TYPE_CHECKING:
    from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink
    from modular_rag.adapters.feedback.postgres_sink import PostgresFeedbackSink
    from modular_rag.adapters.observability.otel_meter import OtelMeter
    from modular_rag.adapters.observability.otel_tracing import OtelTracer
    from modular_rag.adapters.review.postgres_queue import PostgresReviewQueue
    from modular_rag.contracts.manifests import ComponentConfig
    from modular_rag.retrieval.retrievers.hybrid import HybridRetriever
    from modular_rag.retrieval.retrievers.sparse import PersistentSparseRetriever


def _build_hybrid_retriever(cfg: ComponentConfig) -> HybridRetriever:
    """Resolve `retriever.config.lexical` ("bm25-memory", the default, or
    "sparse-qdrant") into a concrete lexical-backend object *before*
    constructing `HybridRetriever` (Lot 5 — persistent sparse retrieval).

    `HybridRetriever` lives in `retrieval/` and cannot import
    `adapters.vectorstores.qdrant_sparse_store.QdrantSparseStore` directly
    (`scripts/check_layering.py` — domain modules cannot import `adapters/`)
    — this factory function, living in the unrestricted top-level `app/`
    layer, is where that construction has to happen instead, mirroring how
    `orchestration/registry.py`'s post-wiring step injects a `QdrantStore`
    into `VectorRetriever` without either of *them* importing each other.
    """
    from modular_rag.adapters.vectorstores.qdrant_sparse_store import QdrantSparseStore
    from modular_rag.core.errors import ConfigurationError
    from modular_rag.retrieval.retrievers.hybrid import HybridRetriever
    from modular_rag.retrieval.retrievers.sparse import PersistentSparseRetriever

    config = dict(cfg.config)
    lexical = config.pop("lexical", "bm25-memory")
    sparse_collection = config.pop("sparse_collection", None)
    # Codex review (Lot 5, MED-002): these four are QdrantSparseStore-only
    # constructor parameters — HybridRetriever.__init__ does not accept any
    # of them, so leaving them in `config` raised a bare TypeError as soon as
    # a manifest tried to tune the sparse leg (e.g. `lexical: sparse-qdrant`
    # + `avgdl: 128` under the same `retriever.config` block — reproduced
    # before this fix). Popped unconditionally, regardless of which
    # `lexical` backend ends up selected, so they can never leak through to
    # `HybridRetriever(**config)` below.
    sparse_timeout = config.pop("timeout", None)
    sparse_avgdl = config.pop("avgdl", None)
    sparse_k1 = config.pop("k1", None)
    sparse_b = config.pop("b", None)

    lexical_retriever = None
    if lexical == "sparse-qdrant":
        base_collection = config.get("collection", "documents")
        store_kwargs: dict[str, object] = {
            "url": config.get("url", "http://localhost:6333"),
            "collection": sparse_collection or f"{base_collection}_sparse",
            "api_key": config.get("api_key") or None,
        }
        # Only forwarded when explicitly set, so QdrantSparseStore's own
        # constructor defaults (_DEFAULT_AVGDL, k1=1.2, b=0.75, timeout=30.0)
        # stay the single source of truth rather than being duplicated here.
        if sparse_timeout is not None:
            store_kwargs["timeout"] = sparse_timeout
        if sparse_avgdl is not None:
            store_kwargs["avgdl"] = sparse_avgdl
        if sparse_k1 is not None:
            store_kwargs["k1"] = sparse_k1
        if sparse_b is not None:
            store_kwargs["b"] = sparse_b
        lexical_retriever = PersistentSparseRetriever(
            store=QdrantSparseStore(**store_kwargs)  # type: ignore[arg-type]
        )
    elif lexical != "bm25-memory":
        raise ConfigurationError(
            f"Unknown HybridRetriever lexical backend {lexical!r}. "
            "Expected 'bm25-memory' or 'sparse-qdrant'."
        )

    return HybridRetriever(lexical_retriever=lexical_retriever, **config)


def _build_sparse_qdrant_retriever(cfg: ComponentConfig) -> PersistentSparseRetriever:
    """Standalone `retriever.type: "sparse-qdrant"` registration (Lot 5) —
    same store-injection reasoning as `_build_hybrid_retriever` above."""
    from modular_rag.adapters.vectorstores.qdrant_sparse_store import QdrantSparseStore
    from modular_rag.retrieval.retrievers.sparse import PersistentSparseRetriever

    return PersistentSparseRetriever(store=QdrantSparseStore(**cfg.config))


def _build_otel_tracer(cfg: ComponentConfig) -> OtelTracer:
    """ADR-0012 — lazy-imports `OtelTracer` itself (not just the
    `opentelemetry` package it wraps), consistent with every other
    heavy/optional adapter factory in this file."""
    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    return OtelTracer(**cfg.config)


def _build_otel_meter(cfg: ComponentConfig) -> OtelMeter:
    """ADR-0013 — same lazy-import-the-adapter-itself pattern as
    `_build_otel_tracer` above."""
    from modular_rag.adapters.observability.otel_meter import OtelMeter

    return OtelMeter(**cfg.config)


def _build_postgres_audit_sink(cfg: ComponentConfig) -> PostgresAuditSink:
    """Codex review, remaining-risks item (post-implementation, ADR-0011):
    a plain `lambda cfg: PostgresAuditSink(**cfg.config)` would forward
    *any* key a manifest's `audit_sink.config` block happened to contain —
    including `allow_purge`, contradicting ADR-0011's own claim that "the
    manifest-wired instance used by the live application never sets
    `allow_purge=True`." That claim was true only because no shipped
    manifest happens to set it today, not because the wiring path
    structurally prevented it. `allow_purge` is popped unconditionally
    here, before construction, so a manifest can never grant purge rights
    to the request-serving instance regardless of what its `config:` block
    contains — `purge_expired()` stays reachable only through a
    CLI-constructed instance (`mrag audit purge --dsn ...`, never
    `--manifest`), the property this ADR's security design actually
    depends on.
    """
    from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink

    config = dict(cfg.config)
    config.pop("allow_purge", None)
    return PostgresAuditSink(**config)


def _build_postgres_feedback_sink(cfg: ComponentConfig) -> PostgresFeedbackSink:
    """ADR-0014 — same `allow_purge` pop as `_build_postgres_audit_sink`
    above: the manifest-wired instance must never be able to purge, only a
    CLI-constructed one (`mrag feedback purge --dsn ...`)."""
    from modular_rag.adapters.feedback.postgres_sink import PostgresFeedbackSink

    config = dict(cfg.config)
    config.pop("allow_purge", None)
    return PostgresFeedbackSink(**config)


def _build_postgres_review_queue(cfg: ComponentConfig) -> PostgresReviewQueue:
    """ADR-0014 — same `allow_purge` pop as `_build_postgres_audit_sink`."""
    from modular_rag.adapters.review.postgres_queue import PostgresReviewQueue

    config = dict(cfg.config)
    config.pop("allow_purge", None)
    return PostgresReviewQueue(**config)


def register_defaults(reg: ComponentRegistry) -> None:
    from modular_rag.adapters.embeddings.deterministic_embedder import DeterministicEmbedder
    from modular_rag.adapters.embeddings.hf_embedder import HuggingFaceEmbedder
    from modular_rag.adapters.embeddings.openai_embedder import OpenAIEmbedder
    from modular_rag.adapters.lifecycle.postgres_ledger import PostgresLifecycleLedger
    from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
    from modular_rag.core.models.policy import Policy
    from modular_rag.generation.synthesizers.anthropic_gen import AnthropicGenerator
    from modular_rag.generation.synthesizers.deterministic_gen import DeterministicGenerator
    from modular_rag.generation.synthesizers.openai_gen import OpenAIGenerator
    from modular_rag.ingestion.chunkers.adaptive import AdaptiveChunker
    from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker
    from modular_rag.ingestion.lifecycle.in_memory_ledger import InMemoryLifecycleLedger
    from modular_rag.observability import (
        NullMeter,
        NullTelemetry,
        NullTracer,
        StructlogTelemetry,
    )
    from modular_rag.retrieval.rerankers.cross_encoder import CrossEncoderReranker
    from modular_rag.retrieval.retrievers.vector import VectorRetriever
    from modular_rag.security.audit.store import InMemoryAuditSink
    from modular_rag.security.feedback.store import InMemoryFeedbackSink
    from modular_rag.security.filters.basic_guard import BasicSecurityGuard
    from modular_rag.security.policies.human_review import HumanReviewGate
    from modular_rag.security.policies.policy_engine import PolicyEngine
    from modular_rag.security.policies.tenant_isolation import TenantIsolationPolicy
    from modular_rag.security.redaction.patterns import PatternRedactor

    reg.register("chunker", "fixed", lambda cfg: FixedSizeChunker(**cfg.config))
    reg.register("chunker", "adaptive", lambda cfg: AdaptiveChunker(**cfg.config))
    reg.register(
        "embedder", "sentence-transformers", lambda cfg: HuggingFaceEmbedder(**cfg.config)
    )
    reg.register("embedder", "openai-embeddings", lambda cfg: OpenAIEmbedder(**cfg.config))
    reg.register("embedder", "deterministic", lambda cfg: DeterministicEmbedder(**cfg.config))
    reg.register("indexer", "qdrant", lambda cfg: QdrantStore(**cfg.config))
    reg.register("retriever", "vector", lambda cfg: VectorRetriever(**cfg.config))
    reg.register("retriever", "hybrid", _build_hybrid_retriever)
    reg.register("retriever", "sparse-qdrant", _build_sparse_qdrant_retriever)
    reg.register("reranker", "cross-encoder", lambda cfg: CrossEncoderReranker(**cfg.config))
    reg.register("generator", "openai", lambda cfg: OpenAIGenerator(**cfg.config))
    reg.register("generator", "anthropic", lambda cfg: AnthropicGenerator(**cfg.config))
    reg.register("generator", "deterministic", lambda cfg: DeterministicGenerator(**cfg.config))
    reg.register("guard", "basic", lambda cfg: BasicSecurityGuard(**cfg.config))
    reg.register("tenant_policy", "tenant-isolation", lambda cfg: TenantIsolationPolicy())
    reg.register(
        "policy_engine",
        "inline",
        lambda cfg: PolicyEngine([Policy.model_validate(item) for item in cfg.config["policies"]]),
    )
    reg.register("redactor", "patterns", lambda cfg: PatternRedactor())
    reg.register("review_queue", "human-review", lambda cfg: HumanReviewGate(**cfg.config))
    reg.register("review_queue", "postgres-human-review", _build_postgres_review_queue)
    reg.register("audit_sink", "in-memory", lambda cfg: InMemoryAuditSink())
    reg.register("audit_sink", "postgres", _build_postgres_audit_sink)
    reg.register("feedback_sink", "in-memory", lambda cfg: InMemoryFeedbackSink())
    reg.register("feedback_sink", "postgres", _build_postgres_feedback_sink)
    reg.register("telemetry", "structlog", lambda cfg: StructlogTelemetry())
    reg.register("telemetry", "null", lambda cfg: NullTelemetry())
    reg.register("tracer", "otel", _build_otel_tracer)
    reg.register("tracer", "null", lambda cfg: NullTracer())
    reg.register("meter", "otel", _build_otel_meter)
    reg.register("meter", "null", lambda cfg: NullMeter())
    reg.register("lifecycle_ledger", "in-memory", lambda cfg: InMemoryLifecycleLedger())
    reg.register(
        "lifecycle_ledger", "postgres", lambda cfg: PostgresLifecycleLedger(**cfg.config)
    )


def create_default_registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    register_defaults(registry)
    return registry
