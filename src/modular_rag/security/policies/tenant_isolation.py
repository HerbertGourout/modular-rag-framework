"""Tenant-isolation enforcement (Lot 11b, docs/refactoring-plan.md — "enforce
fail-closed policy before indexing, retrieval, and generation... cross-tenant
and policy-engine failure paths... deny-by-default").

Fail-closed by design: a missing tenant identity denies the request outright.
There is deliberately no `try`/`except` anywhere in this class swallowing an
unexpected error into "allow" — any exception here propagates to the caller
(`orchestration/engine.py`), which is itself fail-closed by construction
(an unhandled exception blocks the pipeline, it never falls through to
returning an answer).

Distinct from `PolicyEngine` (`security/policies/policy_engine.py`, V4
policy-as-code): this is the narrower, always-on tenant boundary that every
governed pipeline needs; `PolicyEngine` is the broader, YAML-rule-driven
layer, separately hardened to fail closed in this same lot (see the
try/except added to `PolicyEngine.enforce_query`).
"""
from __future__ import annotations

from modular_rag.core.errors import PolicyViolationError
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


class TenantIsolationPolicy:
    """Enforce that a query carries a known tenant, and that retrieved
    context only contains chunks belonging to that same tenant.

    Registered on `Container.tenant_policy` — optional, mirrors `guard`/
    `audit_sink`'s optionality (Lots 8/10): a pipeline that doesn't configure
    one behaves exactly as it did before this lot.
    """

    def enforce_query(self, query: Query) -> None:
        """Raise if the query has no tenant identity. Call this before any
        retrieval/generation work, not just before returning a result —
        fail-closed means denying early, not filtering late."""
        if not query.tenant_id:
            raise PolicyViolationError(
                "Query has no tenant_id — denied by default (fail-closed, Lot 11b)."
            )

    def enforce_ingest(self, tenant_id: str | None) -> None:
        """Raise if content being indexed has no tenant identity. Same
        fail-closed principle as `enforce_query`, applied at the "before
        indexing" checkpoint the plan names explicitly."""
        if not tenant_id:
            raise PolicyViolationError(
                "Chunk has no tenant_id — denied by default (fail-closed, Lot 11b)."
            )

    def filter_chunks(
        self, tenant_id: str, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Drop any chunk not belonging to `tenant_id`. A chunk with no
        `tenant_id` at all (legacy/unclassified content) is excluded too —
        fail-closed, not treated as implicitly public. Loosening this for
        genuinely `public`-classified content
        (docs/architecture/data-classification-policy.md) is a documented
        follow-up: `Chunk` carries no classification field yet, only
        `tenant_id`, so there is no signal here to distinguish "public" from
        "unclassified."
        """
        return [rc for rc in chunks if rc.chunk.tenant_id == tenant_id]

    def name(self) -> str:
        return "tenant-isolation"
