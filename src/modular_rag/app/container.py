from __future__ import annotations

from typing import Any

import structlog

from modular_rag.contracts.audit import AuditSink
from modular_rag.contracts.chunking import Chunker
from modular_rag.contracts.embeddings import Embedder
from modular_rag.contracts.evaluation import Evaluator
from modular_rag.contracts.generation import Generator
from modular_rag.contracts.indexing import Indexer
from modular_rag.contracts.lifecycle import LifecycleLedger
from modular_rag.contracts.manifests import PipelineManifest
from modular_rag.contracts.reranking import Reranker
from modular_rag.contracts.retrieval import Retriever
from modular_rag.contracts.review import ReviewQueue
from modular_rag.contracts.security import Redactor, SecurityGuard, TenantPolicy
from modular_rag.contracts.telemetry import Telemetry
from modular_rag.core.errors import RegistryError

log = structlog.get_logger(__name__)


class Container:
    """Dependency-injection container: holds all wired components for one pipeline."""

    def __init__(self, manifest: PipelineManifest) -> None:
        self.manifest = manifest
        self._store: dict[str, Any] = {}

    # -- registration --

    def register(self, name: str, component: Any) -> None:
        self._store[name] = component

    def close(self) -> None:
        """Best-effort graceful shutdown (Lot 14, docs/refactoring-plan.md —
        "own and close clients/resources"). Calls `.close()` on every
        registered component that has one (duck-typed — most components,
        e.g. chunkers, don't own a network resource and correctly have no
        `close()` at all). A single component's failure to close is logged
        and does not stop the rest from being closed — a partial shutdown
        leaking one connection is better than one that leaks the rest too
        because it stopped at the first error."""
        for name, component in self._store.items():
            close = getattr(component, "close", None)
            if close is None:
                continue
            try:
                close()
            except Exception as exc:
                log.warning("container.close_failed", component=name, error=str(exc))

    def _get(self, name: str) -> Any:
        if name not in self._store:
            raise RegistryError(f"Component '{name}' is not registered in the container.")
        return self._store[name]

    # -- typed accessors --

    @property
    def chunker(self) -> Chunker:
        return self._get("chunker")

    @property
    def embedder(self) -> Embedder:
        return self._get("embedder")

    @property
    def indexer(self) -> Indexer:
        return self._get("indexer")

    @property
    def retriever(self) -> Retriever:
        return self._get("retriever")

    @property
    def reranker(self) -> Reranker | None:
        return self._store.get("reranker")

    @property
    def generator(self) -> Generator:
        return self._get("generator")

    @property
    def guard(self) -> SecurityGuard | None:
        return self._store.get("guard")

    @property
    def evaluator(self) -> Evaluator | None:
        return self._store.get("evaluator")

    @property
    def telemetry(self) -> Telemetry | None:
        return self._store.get("telemetry")

    @property
    def audit_sink(self) -> AuditSink | None:
        """Optional compliance-audit sink (Lot 10, docs/refactoring-plan.md).
        Distinct from `telemetry`: telemetry receives `Trace` (performance
        observability), this receives `AuditEvent` (compliance evidence).
        Defaults to `None` so existing manifests/tests are unaffected."""
        return self._store.get("audit_sink")

    @property
    def tenant_policy(self) -> TenantPolicy | None:
        """Optional fail-closed tenant-isolation boundary (Lot 11b,
        docs/refactoring-plan.md). Defaults to `None` so existing
        manifests/tests are unaffected, matching `guard`/`audit_sink`'s
        precedent (Lots 8/10)."""
        return self._store.get("tenant_policy")

    @property
    def redactor(self) -> Redactor | None:
        """Optional PII/secret redactor (Lot 11c, docs/refactoring-plan.md —
        "apply configured redaction before storage, logging, and external
        calls"). Defaults to `None`, matching every other optional
        component's precedent."""
        return self._store.get("redactor")

    @property
    def review_queue(self) -> ReviewQueue | None:
        """Optional human-review gate (Lot 11c, docs/refactoring-plan.md —
        "support human review for high-risk outcomes"). Defaults to `None`."""
        return self._store.get("review_queue")

    @property
    def lifecycle_ledger(self) -> LifecycleLedger | None:
        """Optional document-identity/idempotency ledger (Lot 12a,
        docs/refactoring-plan.md). Defaults to `None`: `RAGEngine.ingest()`
        behaves exactly as before (no idempotency check, no update/delete
        tracking) unless one is configured; `RAGEngine.delete_document()`
        requires one and raises `ConfigurationError` otherwise."""
        return self._store.get("lifecycle_ledger")
