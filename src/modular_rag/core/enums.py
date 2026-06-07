from __future__ import annotations

from enum import StrEnum


class Modality(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    AUDIO = "audio"
    VIDEO = "video"
    CODE = "code"


class RetrievalMethod(StrEnum):
    VECTOR = "vector"
    BM25 = "bm25"
    HYBRID = "hybrid"
    GRAPH = "graph"
    MULTIMODAL = "multimodal"


class ChunkingStrategy(StrEnum):
    FIXED = "fixed"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    SECTION = "section"
    ADAPTIVE = "adaptive"
    SEMANTIC = "semantic"


class RoutingStrategy(StrEnum):
    LLM_ONLY = "llm_only"
    SIMPLE_RAG = "simple_rag"
    AGENTIC_RAG = "agentic_rag"
    GRAPH_RAG = "graph_rag"
    MULTIMODAL_RAG = "multimodal_rag"


class PolicyAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REDACT = "redact"
    WARN = "warn"
    REQUIRE_REVIEW = "require_review"


class AgentRole(StrEnum):
    COORDINATOR = "coordinator"
    PLANNER = "planner"
    RETRIEVER = "retriever"
    EXTRACTOR = "extractor"
    SYNTHESIZER = "synthesizer"
    VALIDATOR = "validator"
    CRITIC = "critic"


class GraphRelation(StrEnum):
    DEPENDS_ON = "depends_on"
    CAUSES = "causes"
    IS_PART_OF = "is_part_of"
    WORKS_FOR = "works_for"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    DERIVES_FROM = "derives_from"
