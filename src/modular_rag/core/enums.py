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


class PolicyAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REDACT = "redact"
    WARN = "warn"
    REQUIRE_REVIEW = "require_review"


class DataClassification(StrEnum):
    """Data-sensitivity level (Lot 11a, docs/refactoring-plan.md — "paper-and-fixture
    deliverable; no enforcement code yet"). Vocabulary only: nothing in the codebase
    reads or enforces this yet. Definitions and handling requirements per level are in
    docs/architecture/data-classification-policy.md. Enforcement against this
    vocabulary (deny-by-default on policy-engine error, tenant-scoped filtering) is
    Lot 11b scope, not this one."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class PIICategory(StrEnum):
    """Canonical PII/secret categories referenced by the data-classification policy
    (Lot 11a). Mirrors the label strings already used by
    `security/redaction/patterns.py`'s `_PATTERNS` list plus the two pattern-less
    categories it also redacts (`credit_card`, via Luhn validation) and
    `secret_api_key` (aliased here to the redactor's existing `api_key` label) — this
    enum does not change redaction behavior, it names the same categories for policy
    documents and fixtures to reference without duplicating the regex source of truth.
    """

    EMAIL = "email"
    PHONE = "phone"
    IBAN = "iban"
    API_KEY = "api_key"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"


class GraphRelation(StrEnum):
    DEPENDS_ON = "depends_on"
    CAUSES = "causes"
    IS_PART_OF = "is_part_of"
    WORKS_FOR = "works_for"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    DERIVES_FROM = "derives_from"
