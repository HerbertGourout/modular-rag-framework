from __future__ import annotations

from pathlib import Path

import typer

from modular_rag.app.bootstrap import load_pipeline
from modular_rag.ingestion.pipelines.default import ingest_directory, ingest_path

app = typer.Typer(name="mrag", help="Modular RAG Framework CLI")


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="File or directory to ingest"),  # noqa: B008
    manifest: Path = typer.Option(..., "--manifest", "-m", help="Pipeline manifest YAML"),  # noqa: B008
) -> None:
    """Parse, chunk, embed and index documents from a file or directory."""
    pipeline = load_pipeline(manifest)
    if path.is_dir():
        chunks = ingest_directory(path, pipeline.chunker)
    else:
        chunks = ingest_path(path, pipeline.chunker)
    n = pipeline.ingest_chunks(chunks)
    typer.echo(f"Indexed {n} chunks from {path}.")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to answer"),
    manifest: Path = typer.Option(..., "--manifest", "-m", help="Pipeline manifest YAML"),  # noqa: B008
) -> None:
    """Answer a question using the configured RAG pipeline."""
    pipeline = load_pipeline(manifest)
    answer = pipeline.answer(question)
    typer.echo(f"\n{answer.text}\n")
    for i, citation in enumerate(answer.citations, 1):
        typer.echo(f"  [{i}] {citation.source} (score={citation.score:.3f})")


@app.command()
def version() -> None:
    """Print the framework version."""
    from modular_rag import __version__
    typer.echo(f"modular-rag {__version__}")
