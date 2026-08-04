"""Tests for cli/__init__.py (the `mrag` Typer app).

Monkeypatches load_pipeline (and, for the ingest command, ingest_path/
ingest_directory) so no real adapters or files-on-disk parsing are
exercised — this module only tests the CLI's own wiring. Originally
written in Lot 4 as characterization tests documenting that `ingest`
reached into `pipeline._c.chunker` directly; Lot 8 (docs/refactoring-plan.md)
replaced that with a public `RAGEngine.chunker` property — these are now
regression tests, not characterization.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import modular_rag.cli as cli_module
from modular_rag.cli import app
from modular_rag.core.ids import new_id
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.chunk import Chunk

runner = CliRunner()


class _FakePipeline:
    def __init__(self) -> None:
        self.manifest_id = "fake-pipeline"
        self.chunker = object()
        self.ingested: list[Chunk] = []

    def ingest_chunks(self, chunks: list[Chunk]) -> int:
        self.ingested.extend(chunks)
        return len(chunks)

    def answer(self, question: str) -> Answer:
        return Answer(query_id=new_id(), text=f"answer to: {question}")


def test_version_command_prints_the_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "modular-rag" in result.stdout


def test_ask_command_prints_answer_text_and_citations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = tmp_path / "m.yaml"
    manifest.write_text("id: x\n", encoding="utf-8")
    monkeypatch.setattr(cli_module, "load_pipeline", lambda path: _FakePipeline())

    result = runner.invoke(app, ["ask", "What is RAG?", "--manifest", str(manifest)])

    assert result.exit_code == 0
    assert "answer to: What is RAG?" in result.stdout


def test_ask_command_requires_the_manifest_option(tmp_path: Path) -> None:
    """Characterizes current CLI validation: `--manifest` is a required
    Option, not optional — missing it is a usage error (exit code 2), not a
    friendly message."""
    result = runner.invoke(app, ["ask", "What is RAG?"])

    assert result.exit_code == 2


def test_ingest_command_reports_chunk_count_via_public_chunker_property(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression test: `ingest` now reads `pipeline.chunker` (a public
    property since Lot 8), not `pipeline._c.chunker`."""
    manifest = tmp_path / "m.yaml"
    manifest.write_text("id: x\n", encoding="utf-8")
    doc_file = tmp_path / "doc.txt"
    doc_file.write_text("hello world", encoding="utf-8")
    fake_pipeline = _FakePipeline()
    fake_chunk = Chunk(doc_id=new_id(), content="hello")
    monkeypatch.setattr(cli_module, "load_pipeline", lambda path: fake_pipeline)
    monkeypatch.setattr(cli_module, "ingest_path", lambda path, chunker: [fake_chunk])

    result = runner.invoke(app, ["ingest", str(doc_file), "--manifest", str(manifest)])

    assert result.exit_code == 0
    assert "Indexed 1 chunks" in result.stdout
    assert fake_pipeline.ingested == [fake_chunk]


def test_ingest_command_on_a_directory_uses_ingest_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = tmp_path / "m.yaml"
    manifest.write_text("id: x\n", encoding="utf-8")
    doc_dir = tmp_path / "docs"
    doc_dir.mkdir()
    fake_pipeline = _FakePipeline()
    fake_chunks = [Chunk(doc_id=new_id(), content="a"), Chunk(doc_id=new_id(), content="b")]
    monkeypatch.setattr(cli_module, "load_pipeline", lambda path: fake_pipeline)
    monkeypatch.setattr(cli_module, "ingest_directory", lambda path, chunker: fake_chunks)

    result = runner.invoke(app, ["ingest", str(doc_dir), "--manifest", str(manifest)])

    assert result.exit_code == 0
    assert "Indexed 2 chunks" in result.stdout
