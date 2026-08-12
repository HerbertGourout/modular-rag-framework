"""Application composition for the built-in component catalogue."""

from modular_rag.orchestration.registry import ComponentRegistry


def register_defaults(reg: ComponentRegistry) -> None:
    from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink
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
    from modular_rag.observability import NullTelemetry, StructlogTelemetry
    from modular_rag.retrieval.rerankers.cross_encoder import CrossEncoderReranker
    from modular_rag.retrieval.retrievers.hybrid import HybridRetriever
    from modular_rag.retrieval.retrievers.vector import VectorRetriever
    from modular_rag.security.audit.store import InMemoryAuditSink
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
    reg.register("retriever", "hybrid", lambda cfg: HybridRetriever(**cfg.config))
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
    reg.register("audit_sink", "in-memory", lambda cfg: InMemoryAuditSink())
    reg.register("audit_sink", "postgres", lambda cfg: PostgresAuditSink(**cfg.config))
    reg.register("telemetry", "structlog", lambda cfg: StructlogTelemetry())
    reg.register("telemetry", "null", lambda cfg: NullTelemetry())
    reg.register("lifecycle_ledger", "in-memory", lambda cfg: InMemoryLifecycleLedger())
    reg.register(
        "lifecycle_ledger", "postgres", lambda cfg: PostgresLifecycleLedger(**cfg.config)
    )


def create_default_registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    register_defaults(registry)
    return registry
