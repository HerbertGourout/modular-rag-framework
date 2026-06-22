"""Register all built-in adapters into a ComponentRegistry."""
from __future__ import annotations

from modular_rag.orchestration.registry import ComponentRegistry


def register_defaults(reg: ComponentRegistry) -> None:
    from modular_rag.adapters.embeddings.hf_embedder import HuggingFaceEmbedder
    from modular_rag.adapters.embeddings.openai_embedder import OpenAIEmbedder
    from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
    from modular_rag.eval.scorers.exact_match import ExactMatchEvaluator
    from modular_rag.generation.synthesizers.anthropic_gen import AnthropicGenerator
    from modular_rag.generation.synthesizers.openai_gen import OpenAIGenerator
    from modular_rag.ingestion.chunkers.adaptive import AdaptiveChunker
    from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker
    from modular_rag.retrieval.rerankers.cross_encoder import CrossEncoderReranker
    from modular_rag.retrieval.retrievers.hybrid import HybridRetriever
    from modular_rag.retrieval.retrievers.vector import VectorRetriever
    from modular_rag.security.filters.basic_guard import BasicSecurityGuard

    # chunkers
    reg.register("chunker", "fixed", lambda cfg: FixedSizeChunker(**cfg.config))
    reg.register("chunker", "adaptive", lambda cfg: AdaptiveChunker(**cfg.config))

    # embedders
    reg.register("embedder", "sentence-transformers", lambda cfg: HuggingFaceEmbedder(**cfg.config))
    reg.register("embedder", "openai-embeddings", lambda cfg: OpenAIEmbedder(**cfg.config))

    # indexers
    reg.register("indexer", "qdrant", lambda cfg: QdrantStore(**cfg.config))

    # retrievers
    reg.register("retriever", "vector", lambda cfg: VectorRetriever(**cfg.config))
    reg.register("retriever", "hybrid", lambda cfg: HybridRetriever(**cfg.config))

    # rerankers
    reg.register("reranker", "cross-encoder", lambda cfg: CrossEncoderReranker(**cfg.config))

    # generators
    reg.register("generator", "openai", lambda cfg: OpenAIGenerator(**cfg.config))
    reg.register("generator", "anthropic", lambda cfg: AnthropicGenerator(**cfg.config))

    # security
    reg.register("guard", "basic", lambda cfg: BasicSecurityGuard(**cfg.config))

    # evaluation
    reg.register("evaluator", "exact-match", lambda cfg: ExactMatchEvaluator())
