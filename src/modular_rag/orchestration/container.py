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
    """Dependency-injection container for one wired pipeline."""

    def __init__(self, manifest: PipelineManifest) -> None:
        self.manifest = manifest
        self._store: dict[str, Any] = {}

    def register(self, name: str, component: Any) -> None:
        self._store[name] = component

    def close(self) -> None:
        """Best-effort graceful shutdown of registered resources."""
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
        return self._store.get("audit_sink")

    @property
    def tenant_policy(self) -> TenantPolicy | None:
        return self._store.get("tenant_policy")

    @property
    def redactor(self) -> Redactor | None:
        return self._store.get("redactor")

    @property
    def review_queue(self) -> ReviewQueue | None:
        return self._store.get("review_queue")

    @property
    def lifecycle_ledger(self) -> LifecycleLedger | None:
        return self._store.get("lifecycle_ledger")

    @property
    def policy_engine(self) -> Any | None:
        return self._store.get("policy_engine")

    @property
    def quality_gate(self) -> Any | None:
        return self._store.get("quality_gate")
