"""Cross-platform first run that keeps BM25 ingestion and querying in one process."""

from pathlib import Path

from modular_rag.app.bootstrap import load_application
from modular_rag.app.public import ingest_directory

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "manifests" / "presets" / "local-hybrid-rag.yaml"
DOCUMENTS = Path(__file__).resolve().parent / "docs"


def main() -> None:
    application = load_application(MANIFEST)
    try:
        chunks = ingest_directory(DOCUMENTS, application.chunker)
        print(f"Indexed {application.ingest_chunks(chunks)} chunks")
        answer = application.answer("What is retrieval-augmented generation?")
        print(answer.text)
        for citation in answer.citations:
            print(f"- {citation.source}: {citation.score:.3f}")
    finally:
        application.close()


if __name__ == "__main__":
    main()
