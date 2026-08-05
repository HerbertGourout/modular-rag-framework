"""Concurrency test for BM25Retriever's lock (Lot 14, docs/refactoring-plan.md
— "make ... mutable indexes concurrency-safe"). Proves concurrent index()
calls never lose chunks, and a concurrent retrieve() never crashes on a
torn read of `_chunks`/`_bm25`.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.retrieval.retrievers.bm25 import BM25Retriever


def _chunk(content: str) -> Chunk:
    return Chunk(doc_id=new_id(), content=content)


def test_concurrent_index_calls_never_lose_chunks():
    retriever = BM25Retriever()
    batches = [[_chunk(f"document number {i} about topic {i % 5}")] for i in range(50)]

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(retriever.index, batches))

    assert len(retriever.list_ids()) == 50


def test_concurrent_retrieve_during_indexing_never_raises():
    retriever = BM25Retriever()
    retriever.index([_chunk("initial document about cats")])

    def indexer(i: int):
        retriever.index([_chunk(f"document {i} about dogs")])

    def searcher(_i: int):
        retriever.retrieve(Query(text="cats dogs"), k=5)

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(indexer, i) for i in range(25)]
        futures += [pool.submit(searcher, i) for i in range(25)]
        for f in futures:
            f.result()  # re-raises if any thread raised

    assert len(retriever.list_ids()) == 26  # initial + 25 indexed, none lost
