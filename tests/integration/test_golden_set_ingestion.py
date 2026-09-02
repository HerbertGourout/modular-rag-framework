"""Integration test proving the shipped golden-set corpus can actually be
indexed into a real Qdrant — requires Qdrant on localhost:6333.

CI review finding: `benchmark-gate` died ingesting `core_v1.yaml` because
its `chunk_id` slugs (e.g. "refund-policy-1") were passed straight through
as `Chunk.id`, and Qdrant's point-id format only accepts an unsigned
integer or a UUID. `tests/unit/eval/test_loader.py` never exercised a live
indexer, so this regressed silently while every unit test stayed green.
This test closes that specific gap: it loads the real shipped dataset and
upserts its corpus into a real Qdrant collection, the same way
`scripts/run_benchmark.py` does via `ApplicationService.ingest_chunks()`.
"""
import pytest

from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
from modular_rag.eval.datasets.loader import load_golden_set

COLLECTION = "test_golden_set_ingestion"
DIM = 4


@pytest.mark.integration
def test_golden_set_corpus_ids_are_accepted_by_a_real_qdrant() -> None:
    from scripts.run_benchmark import DEFAULT_DATASET

    golden = load_golden_set(DEFAULT_DATASET)
    assert len(golden.corpus) > 0  # otherwise this test would trivially pass

    store = QdrantStore(url="http://localhost:6333", collection=COLLECTION, vector_size=DIM)
    store.clear()
    try:
        for chunk in golden.corpus:
            chunk.embedding = [1.0, 0.0, 0.0, 0.0]

        indexed = store.index(golden.corpus)

        assert indexed == len(golden.corpus)
        assert sorted(store.list_ids()) == sorted(chunk.id for chunk in golden.corpus)
    finally:
        store.clear()
