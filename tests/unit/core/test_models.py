"""Unit tests for core domain models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from modular_rag.core.enums import (
    DataClassification,
    Modality,
    PIICategory,
    PolicyAction,
    RetrievalMethod,
)
from modular_rag.core.ids import new_id, short_id
from modular_rag.core.models.answer import Answer, Citation
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.document import Document
from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.policy import Policy, PolicyRule
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace, TraceStep

# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------


def test_new_id_is_string_and_unique():
    a, b = new_id(), new_id()
    assert isinstance(a, str)
    assert a != b


def test_short_id_length():
    assert len(short_id()) == 8


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def test_modality_values():
    assert Modality.TEXT == "text"
    assert Modality.IMAGE == "image"


def test_retrieval_method_values():
    assert RetrievalMethod.HYBRID == "hybrid"


def test_policy_action_values():
    assert PolicyAction.DENY == "deny"
    assert PolicyAction.ALLOW == "allow"


def test_data_classification_values():
    """Lot 11a, docs/refactoring-plan.md — vocabulary only, no enforcement yet."""
    assert DataClassification.PUBLIC == "public"
    assert DataClassification.INTERNAL == "internal"
    assert DataClassification.CONFIDENTIAL == "confidential"
    assert DataClassification.RESTRICTED == "restricted"


def test_pii_category_values():
    assert PIICategory.EMAIL == "email"
    assert PIICategory.API_KEY == "api_key"


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


def test_document_defaults():
    doc = Document(source="test.txt", content="hello world")
    assert doc.modality == Modality.TEXT
    assert isinstance(doc.id, str)
    assert doc.metadata == {}


def test_document_is_frozen():
    doc = Document(source="a.txt", content="foo")
    with pytest.raises(ValidationError):
        doc.content = "bar"  # type: ignore[misc]


def test_document_tenant_id_defaults_to_none():
    """Lot 11b, docs/refactoring-plan.md — additive field, existing callers unaffected."""
    assert Document(source="a.txt", content="foo").tenant_id is None


# ---------------------------------------------------------------------------
# Chunk
# ---------------------------------------------------------------------------


def test_chunk_token_estimate():
    doc_id = new_id()
    chunk = Chunk(doc_id=doc_id, content="word " * 20)
    assert chunk.token_estimate == 20  # word count: 20 words


def test_chunk_defaults():
    chunk = Chunk(doc_id=new_id(), content="test")
    assert chunk.modality == Modality.TEXT
    assert chunk.embedding is None
    assert chunk.metadata == {}
    assert chunk.tenant_id is None


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def test_query_frozen():
    q = Query(text="what is RAG?")
    with pytest.raises(ValidationError):
        q.text = "other"  # type: ignore[misc]


def test_query_tenant_id_defaults_to_none():
    """Lot 11b, docs/refactoring-plan.md — additive field, existing callers unaffected."""
    assert Query(text="explain chunking").tenant_id is None


# ---------------------------------------------------------------------------
# RetrievedChunk ordering
# ---------------------------------------------------------------------------


def test_retrieved_chunk_ordering():
    doc_id = new_id()
    c1 = Chunk(doc_id=doc_id, content="first")
    c2 = Chunk(doc_id=doc_id, content="second")
    r1 = RetrievedChunk(chunk=c1, score=0.9, rank=1, retrieval_method=RetrievalMethod.HYBRID)
    r2 = RetrievedChunk(chunk=c2, score=0.5, rank=2, retrieval_method=RetrievalMethod.HYBRID)
    assert r1 < r2


# ---------------------------------------------------------------------------
# Answer & Citation
# ---------------------------------------------------------------------------


def test_answer_defaults():
    q_id = new_id()
    answer = Answer(query_id=q_id, text="The answer is 42.")
    assert answer.citations == []
    assert answer.confidence is None
    assert answer.model is None


def test_citation_passage_truncation_is_not_automatic():
    cit = Citation(chunk_id=new_id(), source="doc.pdf", passage="short passage", score=0.8)
    assert cit.passage == "short passage"


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------


def test_trace_accumulates_steps():
    trace = Trace(query_id=new_id(), pipeline_id="test-pipeline")
    assert trace.totals["input_tokens"] == 0

    step = TraceStep(name="generate", input_tokens=100, output_tokens=50, latency_ms=200.0)
    trace.add_step(step)

    assert len(trace.steps) == 1
    assert trace.totals["input_tokens"] == 100
    assert trace.totals["output_tokens"] == 50
    assert trace.totals["latency_ms"] == 200.0


def test_trace_multiple_steps():
    trace = Trace(query_id=new_id(), pipeline_id="p")
    trace.add_step(TraceStep(name="s1", input_tokens=10, output_tokens=5, latency_ms=50.0))
    trace.add_step(TraceStep(name="s2", input_tokens=20, output_tokens=10, latency_ms=100.0))
    assert trace.totals["input_tokens"] == 30
    assert trace.totals["latency_ms"] == 150.0


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_metrics_summary_omits_none():
    m = Metrics(recall_at_k=0.8, latency_ms=300.0)
    summary = m.summary()
    assert "recall_at_k" in summary
    assert "latency_ms" in summary
    assert "precision_at_k" not in summary
    assert "ndcg" not in summary


def test_metrics_summary_excludes_metadata_fields():
    """Lot 13, docs/refactoring-plan.md: schema_version/failed/failure_reason
    are metadata about the Metrics instance, not a scored quality dimension —
    schema_version and failed both default to non-None values, so without an
    explicit exclusion they'd appear in every summary()."""
    m = Metrics(recall_at_k=0.8)
    summary = m.summary()
    assert "schema_version" not in summary
    assert "failed" not in summary
    assert "failure_reason" not in summary


def test_metrics_defaults_schema_version():
    from modular_rag.core.models.metrics import METRICS_SCHEMA_VERSION

    assert Metrics().schema_version == METRICS_SCHEMA_VERSION


def test_metrics_for_failure_sets_failed_and_reason_with_no_quality_fields():
    m = Metrics.for_failure("engine exploded")
    assert m.failed is True
    assert m.failure_reason == "engine exploded"
    assert m.answer_relevance is None
    assert m.recall_at_k is None


# ---------------------------------------------------------------------------
# Policy & PolicyRule
# ---------------------------------------------------------------------------


def test_policy_sorted_rules():
    r1 = PolicyRule(id="r1", name="low", condition="foo", action=PolicyAction.WARN, priority=1)
    r2 = PolicyRule(id="r2", name="high", condition="bar", action=PolicyAction.DENY, priority=10)
    policy = Policy(id="p1", name="test-policy", rules=[r1, r2])
    sorted_rules = policy.sorted_rules()
    assert sorted_rules[0].priority == 10  # highest priority first


def test_policy_disabled_by_default_is_enabled():
    policy = Policy(id="p1", name="test-policy", rules=[])
    assert policy.enabled is True
