from __future__ import annotations

from collections.abc import Iterable
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
    """Data-sensitivity level (Lot 11a, docs/refactoring-plan.md). Originally
    vocabulary-only ("nothing in the codebase reads or enforces this yet") —
    Lot 20 (docs/refactoring-plan.md, "Data Classification and LLM Egress
    Control") is the first real consumer: `Document.classification`/
    `Chunk.classification` carry it, and
    `security.policies.egress_policy.ManifestEgressPolicy` reads it (via
    `classification_rank()`/`combined_classification()` below) to decide
    whether content may reach a remote embedder/generator. Definitions and
    handling requirements per level are in
    docs/architecture/data-classification-policy.md. Tenant-scoped
    filtering (a related but distinct control) remains Lot 11b's own
    `tenant_id`-based mechanism, not this enum."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


# Lot 20 (docs/refactoring-plan.md, "Data Classification and LLM Egress Control"): the first
# real consumer of DataClassification's ordering. Kept next to the enum itself, not inside
# security/policies/egress_policy.py, so any layer may rank a classification value without
# importing the security domain module (core/ has zero import restrictions elsewhere; every
# layer in this codebase may already import core/).
_CLASSIFICATION_RANK: dict[DataClassification, int] = {
    DataClassification.PUBLIC: 0,
    DataClassification.INTERNAL: 1,
    DataClassification.CONFIDENTIAL: 2,
    DataClassification.RESTRICTED: 3,
}


def classification_rank(level: DataClassification) -> int:
    """Strictly-increasing sensitivity rank (`public` < `internal` <
    `confidential` < `restricted`), for comparing a classification against a
    provider's declared ceiling. Takes a real `DataClassification` only —
    reducing an *unclassified* (`None`) value to a rank is a policy decision
    (what a deployment defaults unclassified content to), not a ranking
    question; see `combined_classification()` below and
    `security.policies.egress_policy.ManifestEgressPolicy`'s own
    `default_classification` handling."""
    return _CLASSIFICATION_RANK[level]


def combined_classification(
    values: Iterable[DataClassification | None],
) -> DataClassification | None:
    """Reduce several classification values (e.g. every chunk in one
    generation call's context) to the single most-restrictive value an
    egress decision should be made against.

    `None` (unclassified) in *any* input makes the combined result `None`
    too, rather than being skipped: a `restricted` chunk sitting next to an
    unlabeled one must not silently average out to something less
    restrictive than "unknown" just because the unlabeled item was ignored.
    An empty input is also `None` — there is nothing to classify as safe.
    """
    materialized = list(values)
    if not materialized or any(v is None for v in materialized):
        return None
    # mypy cannot narrow `list[DataClassification | None]` to
    # `list[DataClassification]` from the `any(v is None ...)` guard above --
    # the `if v is not None` filter on this generator expression re-derives
    # that narrowing directly, since every element reaching `classification_rank`
    # is provably non-None at this point either way.
    return max((v for v in materialized if v is not None), key=classification_rank)


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
