"""Contract conformance tests for `contracts.health.HealthCheckable` (Lot 6
— readiness and resilience).

Every implementation's constructor is network-free (`_get_client()`/
`_get_connection()` are lazy, only fired by a real `check_health()` call),
so Protocol conformance and `name()` are testable here without a live
Qdrant/PostgreSQL — matching the existing convention in
`tests/contract/test_indexer_conformance.py`. Actual `check_health()`
behaviour (healthy/unhealthy verdicts against a real dependency) needs a
live service and is covered by `tests/integration/` instead.
"""
from __future__ import annotations

from modular_rag.adapters.vectorstores.qdrant_sparse_store import QdrantSparseStore
from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
from modular_rag.contracts.health import HealthCheckable
from modular_rag.generation.synthesizers.anthropic_gen import AnthropicGenerator
from modular_rag.generation.synthesizers.openai_gen import OpenAIGenerator
from modular_rag.retrieval.retrievers.hybrid import HybridRetriever
from modular_rag.retrieval.retrievers.sparse import PersistentSparseRetriever

try:
    from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink
    from modular_rag.adapters.lifecycle.postgres_ledger import PostgresLifecycleLedger

    _POSTGRES_IMPLEMENTATIONS = [
        PostgresAuditSink(dsn="postgresql://unused/unused"),
        PostgresLifecycleLedger(dsn="postgresql://unused/unused"),
    ]
except ImportError:
    # psycopg is deliberately opt-in, lazily-imported infrastructure (not in
    # pyproject.toml's v1 extra) — importing the *module* itself doesn't
    # need it (only _get_connection() does), so this except branch should
    # not normally trigger; kept defensive rather than assuming psycopg is
    # always present in every environment this file runs in.
    _POSTGRES_IMPLEMENTATIONS = []

IMPLEMENTATIONS = [
    QdrantStore(),
    QdrantSparseStore(),
    PersistentSparseRetriever(),
    HybridRetriever(),
    *_POSTGRES_IMPLEMENTATIONS,
    # Codex review MEDIUM-002 (Lot 6, third pass): OpenAIGenerator/
    # AnthropicGenerator gained check_health() in the same revision as
    # everything above but were never added here.
    OpenAIGenerator(),
    AnthropicGenerator(),
]


def test_implements_health_checkable_protocol():
    for component in IMPLEMENTATIONS:
        assert isinstance(component, HealthCheckable), type(component).__name__
