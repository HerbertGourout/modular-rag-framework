"""Integration tests for VectorRetriever — requires Qdrant on localhost:6333."""
import pytest

from modular_rag.adapters.embeddings.hf_embedder import HuggingFaceEmbedder
from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.retrieval.retrievers.vector import VectorRetriever

COLLECTION = "test_vector_retriever"
MODEL = "BAAI/bge-small-en-v1.5"


@pytest.fixture(scope="module")
def embedder():
    return HuggingFaceEmbedder(model=MODEL)


@pytest.fixture()
def store(embedder):
    s = QdrantStore(
        url="http://localhost:6333",
        collection=COLLECTION,
        vector_size=embedder.dimensions,
    )
    s.clear()
    yield s
    s.clear()


@pytest.fixture()
def retriever(embedder, store):
    r = VectorRetriever(collection=COLLECTION, url="http://localhost:6333")
    r._embedder = embedder
    r._store = store
    return r


def _index_chunks(store, embedder, texts: list[str]) -> list[Chunk]:
    chunks = []
    embeddings = embedder.embed(texts)
    for text, emb in zip(texts, embeddings):
        c = Chunk(id=new_id(), doc_id="doc-1", content=text)
        c.embedding = emb
        chunks.append(c)
    store.index(chunks)
    return chunks


@pytest.mark.integration
def test_retrieve_returns_ranked_chunks(retriever, store, embedder):
    _index_chunks(store, embedder, [
        "RAG stands for Retrieval Augmented Generation.",
        "Paris is the capital of France.",
        "Python is a programming language.",
    ])
    query = Query(text="What is RAG?")
    results = retriever.retrieve(query, k=3)

    assert len(results) > 0
    assert results[0].rank == 1
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True), "Results must be sorted by score descending"
    assert "RAG" in results[0].chunk.content


@pytest.mark.integration
def test_retrieve_raises_without_embedder():
    r = VectorRetriever()
    with pytest.raises(Exception, match="embedder"):
        r.retrieve(Query(text="test"), k=5)
