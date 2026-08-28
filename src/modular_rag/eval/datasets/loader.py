"""Golden-set YAML loader (Batch 13, external plan — "Offline benchmark").

`GoldenSet`'s data (`eval/datasets/core_v1.yaml`) declares its corpus as
`Chunk`s with fixed, author-chosen `chunk_id`/`doc_id` values rather than
`Document`s to be chunked at load time. `Chunk.id`/`Document.id` both
default to a fresh random `new_id()` (`core/ids.py`) generated at
construction — a chunking pass over golden-set `Document`s would produce a
*different* random chunk id on every single run, and a golden set's
`relevant_chunk_ids` would have nothing stable to reference. Declaring the
already-chunked `Chunk` objects directly, with explicit ids, sidesteps that
entirely and is what actually makes "reproducible benchmark" (this task's
own acceptance criterion) possible — the same YAML always ingests to the
exact same chunk ids, on any machine, forever.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from modular_rag.core.errors import EvaluationError
from modular_rag.core.models.chunk import Chunk
from modular_rag.eval.runners.benchmark import GOLDEN_SET_SCHEMA_VERSION, BenchmarkCase, GoldenSet

# Codex review (pass 1, MEDIUM-001): the only two case types
# `BenchmarkRunner.run()` actually branches on (`benchmark.py`'s own
# docstring) — anything else silently fell through as an implicit "qa" case,
# with no error, before this loader validated it.
_VALID_CASE_TYPES = frozenset({"qa", "safety"})


def load_golden_set(path: str | Path) -> GoldenSet:
    """Parse a golden-set YAML file (see `eval/datasets/core_v1.yaml` for the
    real, documented shape) into a `GoldenSet` — its `.cases` for
    `BenchmarkRunner.run()` and its `.corpus` (`list[Chunk]`) to ingest
    beforehand via `ApplicationService.ingest_chunks()`/
    `RAGEngine.ingest_chunks()`.

    Raises `EvaluationError` for a missing file, invalid YAML, or a
    `schema_version` this loader doesn't recognize — fail loudly rather than
    silently misinterpreting an unexpected shape.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise EvaluationError(f"Golden set not found: {file_path}")
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise EvaluationError(f"Invalid YAML in golden set {file_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise EvaluationError(f"Golden set {file_path} must be a YAML mapping at the top level.")

    schema_version = raw.get("schema_version", GOLDEN_SET_SCHEMA_VERSION)
    if schema_version != GOLDEN_SET_SCHEMA_VERSION:
        raise EvaluationError(
            f"Golden set {file_path} declares schema_version={schema_version!r}, "
            f"but this loader only understands {GOLDEN_SET_SCHEMA_VERSION!r}."
        )

    corpus = [_parse_chunk(item, file_path) for item in raw.get("corpus", [])]
    corpus_ids = {chunk.id for chunk in corpus}
    cases = [_parse_case(item, file_path, corpus_ids) for item in raw.get("cases", [])]
    if not cases:
        raise EvaluationError(f"Golden set {file_path} declares zero cases.")

    return GoldenSet(
        name=raw.get("name", file_path.stem),
        cases=cases,
        schema_version=schema_version,
        domain=raw.get("domain", "default"),
        corpus=corpus,
    )


def _parse_chunk(item: dict[str, Any], file_path: Path) -> Chunk:
    try:
        return Chunk(id=item["chunk_id"], doc_id=item["doc_id"], content=item["content"])
    except KeyError as exc:
        raise EvaluationError(
            f"Golden set {file_path}: corpus entry missing required field {exc}."
        ) from exc


def _parse_case(item: dict[str, Any], file_path: Path, corpus_ids: set[str]) -> BenchmarkCase:
    """Codex review (pass 1, MEDIUM-001): this used to copy `case_type`/
    `expect_block`/`relevant_chunk_ids` without validating their shape. A
    typo like `case_type: saftey` silently fell through as an ordinary "qa"
    case (only exact equality with `"safety"` branches in
    `BenchmarkRunner.run()`), a quoted `"true"` string was accepted as a
    truthy `expect_block`, and a string `relevant_chunk_ids` value was split
    into individual characters by `list(...)` instead of raising. Each of
    those silently corrupts scoring while the dataset still "loads
    successfully" — validated explicitly here instead, fail-loud like every
    other malformed-shape case this loader already rejects."""
    try:
        question = item["question"]
    except KeyError as exc:
        raise EvaluationError(
            f"Golden set {file_path}: case missing required field {exc}."
        ) from exc

    case_type = item.get("case_type", "qa")
    if case_type not in _VALID_CASE_TYPES:
        raise EvaluationError(
            f"Golden set {file_path}: case {question!r} has invalid "
            f"case_type={case_type!r}; must be one of {sorted(_VALID_CASE_TYPES)}."
        )

    expect_block = item.get("expect_block", False)
    if not isinstance(expect_block, bool):
        raise EvaluationError(
            f"Golden set {file_path}: case {question!r} has a non-boolean "
            f"expect_block={expect_block!r}."
        )

    relevant_chunk_ids = item.get("relevant_chunk_ids", [])
    if not isinstance(relevant_chunk_ids, list) or not all(
        isinstance(cid, str) for cid in relevant_chunk_ids
    ):
        raise EvaluationError(
            f"Golden set {file_path}: case {question!r} has a malformed "
            f"relevant_chunk_ids (expected a list of strings, got "
            f"{relevant_chunk_ids!r})."
        )
    unknown_ids = [cid for cid in relevant_chunk_ids if cid not in corpus_ids]
    if unknown_ids:
        raise EvaluationError(
            f"Golden set {file_path}: case {question!r} declares "
            f"relevant_chunk_ids not present in the corpus: {unknown_ids!r}."
        )

    return BenchmarkCase(
        question=question,
        expected_answer=item.get("expected_answer", ""),
        relevant_chunk_ids=relevant_chunk_ids,
        case_type=case_type,
        expect_block=expect_block,
    )
