from __future__ import annotations

from typing import Any

from modular_rag.contracts.audit import AuditSink
from modular_rag.contracts.chunking import Chunker
from modular_rag.contracts.embeddings import Embedder
from modular_rag.contracts.evaluation import Evaluator
from modular_rag.contracts.generation import Generator
from modular_rag.contracts.indexing import Indexer
from modular_rag.contracts.manifests import PipelineManifest
from modular_rag.contracts.reranking import Reranker
from modular_rag.contracts.retrieval import Retriever
from modular_rag.contracts.security import SecurityGuard
from modular_rag.contracts.telemetry import Telemetry
from modular_rag.core.errors import RegistryError


class Container:
    """Dependency-injection container: holds all wired components for one pipeline."""

    def __init__(self, manifest: PipelineManifest) -> None:
        self.manifest = manifest
        self._store: dict[str, Any] = {}

    # -- registration --

    def register(self, name: str, component: Any) -> None:
        self._store[name] = component

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
