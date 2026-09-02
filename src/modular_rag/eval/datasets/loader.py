"""Golden-set YAML loader (Batch 13, external plan — "Offline benchmark").

`GoldenSet`'s data (`eval/datasets/core_v1.yaml`) declares its corpus as
`Chunk`s with fixed, author-chosen `chunk_id`/`doc_id` slugs rather than
`Document`s to be chunked at load time. `Chunk.id`/`Document.id` both
default to a fresh random `new_id()` (`core/ids.py`) generated at
construction — a chunking pass over golden-set `Document`s would produce a
*different* random chunk id on every single run, and a golden set's
`relevant_chunk_ids` would have nothing stable to reference. Declaring the
already-chunked `Chunk` objects directly, with explicit ids, sidesteps that
entirely and is what actually makes "reproducible benchmark" (this task's
own acceptance criterion) possible — the same YAML always ingests to the
exact same chunk ids, on any machine, forever.

CI review finding: a human-readable slug like `chunk_id: refund-policy-1`
was previously passed straight through as `Chunk.id` — Qdrant's point-id
format only accepts an unsigned integer or a UUID, so `QdrantStore.index()`
rejected every golden-set chunk during `benchmark-gate`
("value refund-policy-1 is not a valid point ID"). No unit test ever
exercised a live indexer, so this regressed silently. Fixed here, not in
the YAML: `chunk_id`/`doc_id` slugs stay the readable, hand-editable
identifiers a human cross-references in `relevant_chunk_ids`; this loader
deterministically derives a UUID5 from `(golden_set_name, slug)` for the
real `Chunk.id`/`doc_id` used everywhere downstream (indexing, retrieval,
scoring) — same slug, same golden set, same UUID, every run, on any
machine, exactly preserving the reproducibility guarantee above while
actually satisfying Qdrant's id format. The original slug is kept on
`Chunk.metadata["golden_set_alias"]` for readability in reports/logs.
"""
from __future__ import annotations

import uuid
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

# Fixed, arbitrary namespace for uuid.uuid5() — any constant UUID works here;
# what matters is that it never changes, so (golden_set_name, slug) always
# derives the same id on every machine, forever.
_ID_NAMESPACE = uuid.UUID("6f6b1a2e-6e2b-4f9b-9a1e-8f5c2a2d5b7e")


def _derive_id(golden_set_name: str, slug: str) -> str:
    """Deterministic UUID5 derived from the golden set's name and a
    human-readable slug — valid as a Qdrant point id, unlike the slug
    itself. See this module's own docstring for the CI failure this fixes."""
    return str(uuid.uuid5(_ID_NAMESPACE, f"{golden_set_name}:{slug}"))


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

    name = raw.get("name", file_path.stem)
    raw_corpus = raw.get("corpus", [])
    corpus = [_parse_chunk(item, file_path, name) for item in raw_corpus]
    # Maps each author-chosen slug to the derived id actually stored on the
    # corresponding Chunk — used below to translate `relevant_chunk_ids`
    # (still written as slugs in the YAML) to the same derived ids that a
    # real retriever will return, while keeping "unknown id" error messages
    # readable (reporting the original slug, not an opaque UUID).
    slug_to_id = {
        item["chunk_id"]: chunk.id for item, chunk in zip(raw_corpus, corpus, strict=True)
    }
    cases = [_parse_case(item, file_path, slug_to_id) for item in raw.get("cases", [])]
    if not cases:
        raise EvaluationError(f"Golden set {file_path} declares zero cases.")

    return GoldenSet(
        name=name,
        cases=cases,
        schema_version=schema_version,
        domain=raw.get("domain", "default"),
        corpus=corpus,
    )


def _parse_chunk(item: dict[str, Any], file_path: Path, golden_set_name: str) -> Chunk:
    try:
        chunk_slug = item["chunk_id"]
        doc_slug = item["doc_id"]
        content = item["content"]
    except KeyError as exc:
        raise EvaluationError(
            f"Golden set {file_path}: corpus entry missing required field {exc}."
        ) from exc
    return Chunk(
        id=_derive_id(golden_set_name, chunk_slug),
        doc_id=_derive_id(golden_set_name, doc_slug),
        content=content,
        metadata={"golden_set_alias": chunk_slug},
    )


def _parse_case(
    item: dict[str, Any], file_path: Path, slug_to_id: dict[str, str]
) -> BenchmarkCase:
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

    relevant_chunk_slugs = item.get("relevant_chunk_ids", [])
    if not isinstance(relevant_chunk_slugs, list) or not all(
        isinstance(cid, str) for cid in relevant_chunk_slugs
    ):
        raise EvaluationError(
            f"Golden set {file_path}: case {question!r} has a malformed "
            f"relevant_chunk_ids (expected a list of strings, got "
            f"{relevant_chunk_slugs!r})."
        )
    unknown_ids = [cid for cid in relevant_chunk_slugs if cid not in slug_to_id]
    if unknown_ids:
        raise EvaluationError(
            f"Golden set {file_path}: case {question!r} declares "
            f"relevant_chunk_ids not present in the corpus: {unknown_ids!r}."
        )

    return BenchmarkCase(
        question=question,
        expected_answer=item.get("expected_answer", ""),
        relevant_chunk_ids=[slug_to_id[slug] for slug in relevant_chunk_slugs],
        case_type=case_type,
        expect_block=expect_block,
    )
