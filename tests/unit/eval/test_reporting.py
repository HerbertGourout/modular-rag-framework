"""Unit tests for eval/reporting.py (Batch 13, external plan — "Offline
benchmark")."""
from __future__ import annotations

from pathlib import Path

from modular_rag.core.models.metrics import Metrics
from modular_rag.eval.reporting import (
    build_report_payload,
    load_json_report,
    render_markdown_report,
    write_json_report,
)
from modular_rag.eval.runners.benchmark import BenchmarkReport


def _report() -> BenchmarkReport:
    return BenchmarkReport(
        total=3,
        metrics_per_case=[
            Metrics(answer_relevance=0.9, recall_at_k=0.8, ndcg=0.7, faithfulness=0.6),
            Metrics(safety_score=1.0, latency_ms=42.0),
            Metrics.for_failure("boom", error_stage="retrieval"),
        ],
    )


def test_build_report_payload_includes_quality_and_cost_sections() -> None:
    payload = build_report_payload(
        _report(),
        dataset_name="core-v1",
        dataset_schema_version="1.0",
        manifest_path="some/manifest.yaml",
        commit_sha="abc123",
    )

    assert payload["dataset_name"] == "core-v1"
    assert payload["commit_sha"] == "abc123"
    assert payload["total_cases"] == 3
    assert payload["failed_count"] == 1
    assert payload["error_stage_counts"] == {"retrieval": 1}
    assert "avg_answer_relevance" in payload["quality"]
    assert "avg_latency_ms" in payload["cost"]


def test_write_and_load_json_report_round_trips(tmp_path: Path) -> None:
    payload = build_report_payload(
        _report(), dataset_name="core-v1", dataset_schema_version="1.0", manifest_path="m.yaml"
    )
    path = tmp_path / "report.json"

    write_json_report(payload, path)
    loaded = load_json_report(path)

    assert loaded == payload


def test_load_json_report_returns_none_for_a_missing_file(tmp_path: Path) -> None:
    assert load_json_report(tmp_path / "does-not-exist.json") is None


def test_render_markdown_report_without_a_baseline_shows_no_delta() -> None:
    payload = build_report_payload(
        _report(), dataset_name="core-v1", dataset_schema_version="1.0", manifest_path="m.yaml"
    )

    markdown = render_markdown_report(payload)

    assert "core-v1" in markdown
    assert "| avg_answer_relevance |" in markdown
    assert "—" in markdown  # no baseline -> placeholder, not a fabricated delta


def test_render_markdown_report_with_a_baseline_shows_a_delta() -> None:
    payload = build_report_payload(
        _report(), dataset_name="core-v1", dataset_schema_version="1.0", manifest_path="m.yaml"
    )
    baseline = {"quality": {**payload["quality"], "avg_answer_relevance": 0.5}, "cost": payload["cost"]}

    markdown = render_markdown_report(payload, baseline=baseline)

    assert "+0.4" in markdown  # 0.9 - 0.5
