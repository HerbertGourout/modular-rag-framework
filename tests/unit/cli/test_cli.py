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
    def __init__(self, *, answer_error: Exception | None = None) -> None:
        self.manifest_id = "fake-pipeline"
        self.chunker = object()
        self.ingested: list[Chunk] = []
        self._answer_error = answer_error
        self.last_tenant_id: str | None = "unset"
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def ingest_chunks(self, chunks: list[Chunk]) -> int:
        self.ingested.extend(chunks)
        return len(chunks)

    def answer(self, question: str, tenant_id: str | None = None) -> Answer:
        self.last_tenant_id = tenant_id
        if self._answer_error is not None:
            raise self._answer_error
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


def test_ask_command_threads_the_tenant_id_option_into_the_pipeline_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = tmp_path / "m.yaml"
    manifest.write_text("id: x\n", encoding="utf-8")
    fake_pipeline = _FakePipeline()
    monkeypatch.setattr(cli_module, "load_pipeline", lambda path: fake_pipeline)

    result = runner.invoke(
        app,
        ["ask", "What is RAG?", "--manifest", str(manifest), "--tenant-id", "acme-corp"],
    )

    assert result.exit_code == 0
    assert fake_pipeline.last_tenant_id == "acme-corp"
    assert fake_pipeline.closed is True


def test_ask_command_exits_with_a_typed_code_on_a_security_denial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Lot 16a (docs/refactoring-plan.md — "CLI exit codes"): previously
    every failure surfaced as an uncaught traceback with exit code 1,
    indistinguishable from a genuine bug. A security-guard/policy denial now
    exits 3, with a clean one-line message on stderr instead of a
    traceback."""
    from modular_rag.core.errors import SecurityError

    manifest = tmp_path / "m.yaml"
    manifest.write_text("id: x\n", encoding="utf-8")
    fake_pipeline = _FakePipeline(answer_error=SecurityError("blocked by policy"))
    monkeypatch.setattr(cli_module, "load_pipeline", lambda path: fake_pipeline)

    result = runner.invoke(app, ["ask", "hi", "--manifest", str(manifest)])

    assert result.exit_code == 3
    assert "blocked by policy" in result.output


def test_ask_command_exits_with_a_typed_code_on_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from modular_rag.core.errors import ConfigurationError

    manifest = tmp_path / "m.yaml"
    manifest.write_text("id: x\n", encoding="utf-8")

    def _raise(path: object) -> None:
        raise ConfigurationError("bad manifest")

    monkeypatch.setattr(cli_module, "load_pipeline", _raise)

    result = runner.invoke(app, ["ask", "hi", "--manifest", str(manifest)])

    assert result.exit_code == 2
    assert "bad manifest" in result.output


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


def test_validate_command_reports_ok_for_the_runnable_preset() -> None:
    result = runner.invoke(app, ["validate", "manifests/presets/local-hybrid-rag.yaml"])

    assert result.exit_code == 0
    assert "OK:" in result.stdout


def test_validate_command_reports_capability_errors_for_an_unregistered_type(
    tmp_path: Path,
) -> None:
    bad_manifest = tmp_path / "bad.yaml"
    bad_manifest.write_text(
        "id: bad-pipeline\nembedder:\n  type: does-not-exist\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["validate", str(bad_manifest)])

    assert result.exit_code == 1
    assert "does-not-exist" in result.stdout


def test_validate_command_reports_invalid_for_unresolved_interpolation(
    tmp_path: Path,
) -> None:
    bad_manifest = tmp_path / "bad.yaml"
    bad_manifest.write_text(
        "id: bad-pipeline\nindexer:\n  type: qdrant\n  config:\n    url: ${TOTALLY_UNSET_VAR}\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["validate", str(bad_manifest)])

    assert result.exit_code == 1
    assert "INVALID" in result.stdout


def test_manifest_schema_command_prints_valid_json_schema() -> None:
    import json

    result = runner.invoke(app, ["manifest-schema"])

    assert result.exit_code == 0
    schema = json.loads(result.stdout)
    assert schema["title"] == "PipelineManifest"
    assert schema["additionalProperties"] is False


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
