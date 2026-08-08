from __future__ import annotations

from pathlib import Path

import typer

from modular_rag.app.public import (
    ConfigurationError,
    ModularRAGError,
    PipelineManifest,
    SecurityError,
    create_default_registry,
    ingest_directory,
    ingest_path,
    resolve_manifest,
    validate_capabilities,
)
from modular_rag.app.public import load_application as load_pipeline

app = typer.Typer(name="mrag", help="Modular RAG Framework CLI")

# Typed exit codes (Lot 16a, docs/refactoring-plan.md — "CLI exit codes").
# Previously every failure mode (a typo'd manifest path, a security-guard
# denial, an ingestion/retrieval crash, a genuine bug) surfaced identically
# as an uncaught Python traceback with exit code 1 — a caller scripting
# against this CLI (CI, a shell pipeline) could not distinguish "your input
# was invalid" from "the framework broke" without parsing stderr text.
EXIT_CONFIGURATION_ERROR = 2
EXIT_SECURITY_DENIAL = 3
EXIT_OPERATION_ERROR = 4


def _exit_code_for(exc: Exception) -> int:
    if isinstance(exc, ConfigurationError):
        return EXIT_CONFIGURATION_ERROR
    if isinstance(exc, SecurityError):
        return EXIT_SECURITY_DENIAL
    if isinstance(exc, ModularRAGError):
        return EXIT_OPERATION_ERROR
    return 1


def _close_application(application: object | None) -> None:
    close = getattr(application, "close", None)
    if close is not None:
        close()


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="File or directory to ingest"),  # noqa: B008
    manifest: Path = typer.Option(..., "--manifest", "-m", help="Pipeline manifest YAML"),  # noqa: B008
) -> None:
    """Parse, chunk, embed and index documents from a file or directory."""
    pipeline = None
    try:
        pipeline = load_pipeline(manifest)
        if path.is_dir():
            chunks = ingest_directory(path, pipeline.chunker)
        else:
            chunks = ingest_path(path, pipeline.chunker)
        n = pipeline.ingest_chunks(chunks)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    finally:
        _close_application(pipeline)
    typer.echo(f"Indexed {n} chunks from {path}.")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to answer"),
    manifest: Path = typer.Option(..., "--manifest", "-m", help="Pipeline manifest YAML"),  # noqa: B008
    tenant_id: str | None = typer.Option(
        None, "--tenant-id", help="Tenant identity for a tenant_policy-enabled manifest"
    ),
) -> None:
    """Answer a question using the configured RAG pipeline."""
    pipeline = None
    try:
        pipeline = load_pipeline(manifest)
        answer = pipeline.answer(question, tenant_id=tenant_id)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for(exc)) from exc
    finally:
        _close_application(pipeline)
    typer.echo(f"\n{answer.text}\n")
    for i, citation in enumerate(answer.citations, 1):
        typer.echo(f"  [{i}] {citation.source} (score={citation.score:.3f})")


@app.command()
def validate(
    manifest: Path = typer.Argument(..., help="Pipeline manifest YAML to validate"),  # noqa: B008
) -> None:
    """Validate a manifest: schema + capability checks, no wiring/instantiation.

    Added in Lot 9 (docs/refactoring-plan.md) — catches a typo'd or
    unregistered component type, unresolved `${VAR}`/`secret://` reference,
    or unknown field, before a full pipeline load fails deep in wiring.
    """
    try:
        # ConfigurationError is the base of ManifestError and covers
        # interpolate()'s unresolved ${VAR}/secret:// failures too — both
        # are "this manifest, as given, is invalid," not distinct cases.
        pipeline_manifest = resolve_manifest(manifest)
    except ConfigurationError as exc:
        typer.echo(f"INVALID: {exc}")
        raise typer.Exit(code=1) from exc

    errors = validate_capabilities(pipeline_manifest, create_default_registry())
    if errors:
        typer.echo(f"INVALID: {manifest} — capability errors:")
        for err in errors:
            typer.echo(f"  - {err}")
        raise typer.Exit(code=1)

    typer.echo(
        f"OK: {manifest} is valid "
        f"(schema version {pipeline_manifest.version}, id={pipeline_manifest.id})"
    )


@app.command(name="manifest-schema")
def manifest_schema() -> None:
    """Print the PipelineManifest JSON Schema (for IDE tooling / diffing
    against manifests/schema/pipeline-manifest.schema.json)."""
    import json

    typer.echo(json.dumps(PipelineManifest.model_json_schema(), indent=2))


@app.command()
def version() -> None:
    """Print the framework version."""
    from modular_rag import __version__
    typer.echo(f"modular-rag {__version__}")
