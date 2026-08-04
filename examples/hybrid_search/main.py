"""hybrid_search — retrieval-only example, no LLM key required.

Ingests documents and runs the same query through the vector-only, BM25-only,
and RRF-fused hybrid retrievers side by side, so you can see what each
retrieval method contributes.

Run:
    cd examples/hybrid_search
    python main.py ingest ./docs
    python main.py search "what is semantic search?"

Requirements:
    pip install -e "../../[v1]"
    docker run -d -p 6333:6333 qdrant/qdrant

Note: unlike simple_qa, this example never calls the generator, so no LLM API
key is needed — only Qdrant.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

_HERE = Path(__file__).parent
_FRAMEWORK_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "src"))

MANIFEST = _FRAMEWORK_ROOT / "manifests" / "presets" / "local-hybrid-rag.yaml"


def cmd_ingest(docs_path: str) -> None:
    from modular_rag.app.bootstrap import load_pipeline
    from modular_rag.ingestion.chunkers.adaptive import AdaptiveChunker
    from modular_rag.ingestion.pipelines.default import ingest_directory, ingest_path

    pipeline = load_pipeline(str(MANIFEST))
    path = Path(docs_path)

    if not path.exists():
        print(f"ERROR: path does not exist: {path}", file=sys.stderr)
        sys.exit(1)

    chunker = AdaptiveChunker()
    chunks = ingest_directory(path, chunker) if path.is_dir() else ingest_path(path, chunker)
    n = pipeline.ingest_chunks(chunks)
    print(f"Indexed {n} chunks from {path}")


def _print_results(label: str, results) -> None:
    print(f"\n{label} (top {len(results)}):")
    if not results:
        print("  (no results)")
        return
    for r in results:
        passage = textwrap.shorten(r.chunk.content, width=100, placeholder="...")
        source = r.chunk.metadata.get("source", r.chunk.doc_id)
        print(f"  #{r.rank}  score={r.score:.4f}  {source}")
        print(f"       {passage}")


def cmd_search(question: str, k: int) -> None:
    from modular_rag.app.bootstrap import load_pipeline
    from modular_rag.core.models.query import Query

    pipeline = load_pipeline(str(MANIFEST))
    query = Query(text=question)

    # Reach into the already-wired HybridRetriever's sub-retrievers to compare
    # each method individually — read-only introspection for demo purposes,
    # not component wiring (that already happened inside load_pipeline()).
    # `pipeline.retriever` is the public accessor (Lot 8); `_vector`/`_bm25`
    # below are HybridRetriever's own internals, with no public equivalent —
    # an intentional exception for this side-by-side demo, not a pattern to
    # copy into production code.
    hybrid = pipeline.retriever
    vector_results = hybrid._vector.retrieve(query, k=k)
    bm25_results = hybrid._bm25.retrieve(query, k=k)
    hybrid_results = pipeline.retrieve(question, k=k)

    print(f"Query: {question}")
    _print_results("Vector-only (semantic)", vector_results)
    _print_results("BM25-only (lexical)", bm25_results)
    _print_results("Hybrid (RRF-fused)", hybrid_results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid search example — Modular RAG Framework")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest documents into the pipeline")
    ingest_parser.add_argument("path", help="Path to file or directory to ingest")

    search_parser = subparsers.add_parser("search", help="Compare retrieval methods for a query")
    search_parser.add_argument("question", help="Search query")
    search_parser.add_argument("-k", type=int, default=5, help="Number of results per method")

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args.path)
    elif args.command == "search":
        cmd_search(args.question, args.k)


if __name__ == "__main__":
    main()
