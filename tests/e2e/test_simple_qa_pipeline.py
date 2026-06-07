"""End-to-end test for the simple_qa pipeline — requires Qdrant + MRAG_OPENAI_API_KEY."""
import pathlib

import pytest

from modular_rag.app.bootstrap import load_pipeline
from modular_rag.ingestion.chunkers.adaptive import AdaptiveChunker
from modular_rag.ingestion.pipelines.default import ingest_directory

MANIFEST = pathlib.Path(__file__).parents[2] / "manifests" / "presets" / "local-hybrid-rag.yaml"
DOCS_DIR = pathlib.Path(__file__).parents[2] / "examples" / "simple_qa" / "docs"


@pytest.fixture(scope="module")
def pipeline():
    return load_pipeline(str(MANIFEST))


@pytest.mark.e2e
def test_ingest_and_answer(pipeline):
    chunks = ingest_directory(str(DOCS_DIR), AdaptiveChunker())
    assert chunks, "No chunks produced — check docs/ directory"

    pipeline.ingest_chunks(chunks)

    answer = pipeline.answer("What is RAG?")
    assert answer.text, "Answer text must not be empty"
    assert len(answer.citations) > 0, "At least one citation expected"
    assert answer.trace_id, "Trace ID must be set"


@pytest.mark.e2e
def test_retrieve_only(pipeline):
    results = pipeline.retrieve("retrieval augmented generation", k=5)
    assert len(results) > 0
    assert results[0].score > 0
