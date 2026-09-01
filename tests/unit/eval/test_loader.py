"""Unit tests for eval/datasets/loader.py (Batch 13, external plan —
"Offline benchmark")."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from modular_rag.core.errors import EvaluationError
from modular_rag.eval.datasets.loader import load_golden_set


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "golden.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_corpus_with_fixed_chunk_and_doc_ids(tmp_path: Path) -> None:
    """CI review finding: `chunk_id`/`doc_id` slugs (`c1`/`d1`) are no
    longer used verbatim as `Chunk.id`/`doc_id` — Qdrant rejects any point
    id that isn't an unsigned integer or a UUID. The slugs stay the
    readable, hand-editable identifiers in the YAML (and in
    `relevant_chunk_ids`); the loader deterministically derives a UUID5
    from them instead."""
    path = _write(
        tmp_path,
        """
        schema_version: "1.0"
        name: sample
        corpus:
          - chunk_id: c1
            doc_id: d1
            content: hello world
        cases:
          - question: "What is this?"
            expected_answer: "hello world"
            relevant_chunk_ids: [c1]
        """,
    )

    golden = load_golden_set(path)

    assert golden.name == "sample"
    assert len(golden.corpus) == 1
    chunk = golden.corpus[0]
    uuid.UUID(chunk.id)  # valid Qdrant point id, not the raw slug "c1"
    uuid.UUID(chunk.doc_id)
    assert chunk.content == "hello world"
    assert chunk.metadata["golden_set_alias"] == "c1"
    # relevant_chunk_ids must reference the same derived id, not the slug —
    # otherwise scoring would never match a real retriever's results.
    assert golden.cases[0].relevant_chunk_ids == [chunk.id]

    # Deterministic: reloading the identical file yields the identical id.
    assert load_golden_set(path).corpus[0].id == chunk.id


def test_loads_case_type_and_expect_block_with_defaults(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        schema_version: "1.0"
        name: sample
        cases:
          - question: "regular question"
          - question: "attack"
            case_type: safety
            expect_block: true
        """,
    )

    golden = load_golden_set(path)

    assert golden.cases[0].case_type == "qa"
    assert golden.cases[0].expect_block is False
    assert golden.cases[1].case_type == "safety"
    assert golden.cases[1].expect_block is True


def test_missing_file_raises_evaluation_error(tmp_path: Path) -> None:
    with pytest.raises(EvaluationError, match="not found"):
        load_golden_set(tmp_path / "does-not-exist.yaml")


def test_invalid_yaml_raises_evaluation_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "not: valid: yaml: [")

    with pytest.raises(EvaluationError, match="Invalid YAML"):
        load_golden_set(path)


def test_zero_cases_raises_evaluation_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "schema_version: '1.0'\nname: empty\ncases: []\n")

    with pytest.raises(EvaluationError, match="zero cases"):
        load_golden_set(path)


def test_unrecognized_schema_version_raises_evaluation_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        schema_version: "99.0"
        name: sample
        cases:
          - question: "q"
        """,
    )

    with pytest.raises(EvaluationError, match="schema_version"):
        load_golden_set(path)


def test_corpus_entry_missing_a_required_field_raises_evaluation_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        schema_version: "1.0"
        name: sample
        corpus:
          - chunk_id: c1
            content: "no doc_id here"
        cases:
          - question: "q"
        """,
    )

    with pytest.raises(EvaluationError, match="corpus entry missing"):
        load_golden_set(path)


# ---------------------------------------------------------------------------
# Codex review (pass 1, MEDIUM-001): case_type/expect_block/relevant_chunk_ids
# must be schema-validated, not silently misinterpreted.
# ---------------------------------------------------------------------------


def test_unknown_case_type_raises_evaluation_error(tmp_path: Path) -> None:
    """A typo like `case_type: saftey` used to silently fall through as an
    ordinary "qa" case -- BenchmarkRunner.run() only branches on exact
    equality with "safety"."""
    path = _write(
        tmp_path,
        """
        schema_version: "1.0"
        name: sample
        cases:
          - question: "q"
            case_type: saftey
        """,
    )

    with pytest.raises(EvaluationError, match="case_type"):
        load_golden_set(path)


def test_non_boolean_expect_block_raises_evaluation_error(tmp_path: Path) -> None:
    """A quoted `"true"` string used to be accepted as a truthy value with
    no error -- must be a real YAML boolean."""
    path = _write(
        tmp_path,
        """
        schema_version: "1.0"
        name: sample
        cases:
          - question: "q"
            case_type: safety
            expect_block: "true"
        """,
    )

    with pytest.raises(EvaluationError, match="expect_block"):
        load_golden_set(path)


def test_string_relevant_chunk_ids_raises_instead_of_splitting_into_characters(
    tmp_path: Path,
) -> None:
    """`list("c1")` used to silently produce `["c", "1"]` instead of raising
    -- a string value must be rejected, not coerced."""
    path = _write(
        tmp_path,
        """
        schema_version: "1.0"
        name: sample
        corpus:
          - chunk_id: c1
            doc_id: d1
            content: hello
        cases:
          - question: "q"
            relevant_chunk_ids: "c1"
        """,
    )

    with pytest.raises(EvaluationError, match="relevant_chunk_ids"):
        load_golden_set(path)


def test_non_string_element_in_relevant_chunk_ids_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        schema_version: "1.0"
        name: sample
        corpus:
          - chunk_id: "1"
            doc_id: d1
            content: hello
        cases:
          - question: "q"
            relevant_chunk_ids: [1]
        """,
    )

    with pytest.raises(EvaluationError, match="relevant_chunk_ids"):
        load_golden_set(path)


def test_relevant_chunk_id_not_in_corpus_raises_evaluation_error(tmp_path: Path) -> None:
    """A broken reference would otherwise silently produce zero-relevant-hit
    scoring for that case -- fail loud instead."""
    path = _write(
        tmp_path,
        """
        schema_version: "1.0"
        name: sample
        corpus:
          - chunk_id: c1
            doc_id: d1
            content: hello
        cases:
          - question: "q"
            relevant_chunk_ids: [c1, does-not-exist]
        """,
    )

    with pytest.raises(EvaluationError, match="does-not-exist"):
        load_golden_set(path)


def test_empty_relevant_chunk_ids_is_valid(tmp_path: Path) -> None:
    """An intentionally-empty list (e.g. a "no relevant policy exists" case,
    like the real shipped dataset has) must not be rejected."""
    path = _write(
        tmp_path,
        """
        schema_version: "1.0"
        name: sample
        cases:
          - question: "q"
            relevant_chunk_ids: []
        """,
    )

    golden = load_golden_set(path)

    assert golden.cases[0].relevant_chunk_ids == []


def test_the_real_shipped_core_v1_dataset_loads_successfully() -> None:
    """Regression guard: the actual dataset this repo ships must always be
    loadable by this loader, not just a hand-crafted fixture."""
    from scripts.run_benchmark import DEFAULT_DATASET

    golden = load_golden_set(DEFAULT_DATASET)

    assert golden.name == "core-v1"
    assert len(golden.corpus) > 0
    assert len(golden.cases) > 0
    assert any(c.case_type == "safety" for c in golden.cases)
    assert any(c.case_type == "qa" for c in golden.cases)
    # CI regression guard: every corpus chunk/doc id must be a valid Qdrant
    # point id (unsigned int or UUID) — a hand-written slug such as
    # "refund-policy-1" is rejected by Qdrant during ingestion
    # (benchmark-gate's own failure this guards against).
    for chunk in golden.corpus:
        uuid.UUID(chunk.id)
        uuid.UUID(chunk.doc_id)
