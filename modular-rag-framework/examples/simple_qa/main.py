"""simple_qa — end-to-end RAG example.

Run:
    cd examples/simple_qa
    python main.py ingest ./docs
    python main.py ask "What is Modular RAG?"

Requirements:
    pip install -e "../../[v1]"
    export MRAG_OPENAI_API_KEY=sk-...
    docker run -d -p 6333:6333 qdrant/qdrant
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

# Allow running from anywhere by resolving the project root
_HERE = Path(__file__).parent
_FRAMEWORK_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "src"))

MANIFEST = _FRAMEWORK_ROOT / "manifests" / "presets" / "local-hybrid-rag.yaml"


def cmd_ingest(docs_path: str) -> None:
    from modular_rag.app.bootstrap import load_pipeline

    pipeline = load_pipeline(str(MANIFEST))
    path = Path(docs_path)

    if not path.exists():
        print(f"ERROR: path does not exist: {path}", file=sys.stderr)
        sys.exit(1)

    from modular_rag.ingestion.pipelines.default import ingest_directory, ingest_path

    if path.is_dir():
        print(f"Ingesting directory: {path}")
        # Build a chunker matching the manifest
        from modular_rag.ingestion.chunkers.adaptive import AdaptiveChunker

        chunker = AdaptiveChunker()
        chunks = ingest_directory(path, chunker)
    else:
        print(f"Ingesting file: {path}")
        from modular_rag.ingestion.chunkers.adaptive import AdaptiveChunker

        chunker = AdaptiveChunker()
        chunks = ingest_path(path, chunker)

    n = pipeline.ingest([c for c in chunks])
    print(f"Indexed {n} chunks from {path}")


def cmd_ask(question: str) -> None:
    from modular_rag.app.bootstrap import load_pipeline

    pipeline = load_pipeline(str(MANIFEST))
    answer = pipeline.answer(question)

    print(f"\nQuestion: {question}")
    print(f"\nAnswer:\n{textwrap.fill(answer.text, width=80)}\n")

    if answer.citations:
        print("Citations:")
        for i, cit in enumerate(answer.citations, 1):
            source = cit.source or "unknown"
            page = f" (page {cit.page})" if cit.page else ""
            passage = textwrap.shorten(cit.passage, width=100, placeholder="...")
            print(f"  [{i}] {source}{page} — score: {cit.score:.3f}")
            print(f"       {passage}")
    else:
        print("(No citations)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simple QA example — Modular RAG Framework"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest documents into the pipeline")
    ingest_parser.add_argument("path", help="Path to file or directory to ingest")

    ask_parser = subparsers.add_parser("ask", help="Ask a question")
    ask_parser.add_argument("question", help="Question to answer")

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args.path)
    elif args.command == "ask":
        cmd_ask(args.question)


if __name__ == "__main__":
    main()
