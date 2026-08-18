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
    """VECTOR/BM25/HYBRID/SPARSE are the only values any registered retriever
    ever sets (Étape 8 cleanup, 2026-08-07, plus SPARSE added Lot 5): GRAPH and
    MULTIMODAL described delegated capabilities (ADR-0005 §5.2) with zero
    producing code and zero consumers anywhere in this codebase — removed
    rather than kept as an unreachable enum value. Restorable via git history
    if a native graph/multimodal retriever is ever built. SPARSE is the
    opposite case: real producing code
    (`retrieval.retrievers.sparse.PersistentSparseRetriever`) and a real
    consumer (`retrieval.retrievers.hybrid.HybridRetriever`'s
    `lexical="sparse-qdrant"` option)."""

    VECTOR = "vector"
    BM25 = "bm25"
    HYBRID = "hybrid"
    SPARSE = "sparse"


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


class ReadinessState(StrEnum):
    """Pipeline-level readiness (Lot 6 — readiness and resilience), reported
    by `orchestration.container.Container.check_readiness()` / exposed via
    `GET /ready`. Distinct from `CircuitState` (`core/resilience.py`), which
    is per-dependency and per-adapter-instance, not an aggregate pipeline
    verdict.

    HEALTHY: every checked dependency reachable.
    DEGRADED: a non-critical dependency is unreachable (e.g. an optional
      `lifecycle_ledger`, or `HybridRetriever`'s lexical leg — it already
      falls back to vector-only on its own) — still serving traffic.
    UNREADY: a critical dependency is unreachable (e.g. the required
      `indexer`, or a wired `audit_sink` — `RAGEngine._audit()` has no
      try/except around `record()`, so a down audit sink already fails
      every `/answer` call today; DEGRADED would misreport that as
      "still serving traffic"). `/ready` returns HTTP 503 only for this
      state — orchestrators should pull the pod out of rotation.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREADY = "unready"


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
