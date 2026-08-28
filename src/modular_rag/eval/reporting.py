"""Offline-benchmark report writer (Batch 13, external plan — "Offline
benchmark"; not this repo's own docs/refactoring-plan.md Lot numbering).

Produces the two required report shapes from a `BenchmarkReport`:
- `build_report_payload()` + `write_json_report()` — a machine-readable JSON
  artifact keyed by commit, the "comparison between commits" unit
  `scripts/run_benchmark.py` reads back on the next run to diff against.
- `render_markdown_report()` — the human-readable rendering of that same
  payload, optionally against a prior payload as a baseline, so a reviewer
  sees the same before/after numbers a machine-readable diff would show.

Pure and offline: no manifest loading, no engine calls, no git access —
`scripts/run_benchmark.py` (outside `src/modular_rag/`, so it may import
`app`/`orchestration` freely, unlike this domain module — see
`scripts/check_layering.py`) is responsible for gathering `commit_sha`,
`dataset_name`, and `manifest_path` and passing them in.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from modular_rag.eval.runners.benchmark import BenchmarkReport


def build_report_payload(
    report: BenchmarkReport,
    *,
    dataset_name: str,
    dataset_schema_version: str,
    manifest_path: str,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """Assemble the machine-readable report payload. Deliberately a plain
    `dict` (not a pydantic model / new contract) — this is an offline
    reporting artifact, not a runtime data shape any Protocol depends on."""
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit_sha": commit_sha,
        "dataset_name": dataset_name,
        "dataset_schema_version": dataset_schema_version,
        "manifest_path": manifest_path,
        "total_cases": report.total,
        "failed_count": report.failed_count,
        "failure_rate": report.failure_rate,
        "error_stage_counts": report.error_stage_counts(),
        "cost_measured_count": report.cost_measured_count,
        "quality": report.quality_summary(),
        "cost": report.cost_summary(),
    }


def write_json_report(payload: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json_report(path: str | Path) -> dict[str, Any] | None:
    """Read back a previously written payload (e.g. the baseline from a
    prior commit) for comparison. Returns `None` when the file does not
    exist yet — the first-ever run has no baseline to diff against, and
    that is not an error."""
    file_path = Path(path)
    if not file_path.exists():
        return None
    data: dict[str, Any] = json.loads(file_path.read_text(encoding="utf-8"))
    return data


def render_markdown_report(
    payload: dict[str, Any], baseline: dict[str, Any] | None = None
) -> str:
    """Human-readable rendering of `payload`. When `baseline` (a previously
    written payload) is given, every metric row also shows the delta against
    it — the "comparison between commits" acceptance criterion made visible
    to a human reviewer, not only to a machine-readable JSON diff."""
    lines = [
        "# Offline benchmark report",
        "",
        f"- Dataset: `{payload['dataset_name']}` (schema {payload['dataset_schema_version']})",
        f"- Commit: `{payload.get('commit_sha') or 'unknown'}`",
        f"- Generated: {payload['generated_at']}",
        f"- Manifest: `{payload['manifest_path']}`",
        f"- Cases: {payload['total_cases']} "
        f"({payload['failed_count']} failed, {payload['failure_rate']:.1%} failure rate)",
        "",
    ]

    if payload["error_stage_counts"]:
        lines += ["## Failures by stage", "", "| Stage | Count |", "|---|---|"]
        for stage, count in sorted(payload["error_stage_counts"].items()):
            lines.append(f"| {stage} | {count} |")
        lines.append("")

    baseline_quality = baseline["quality"] if baseline else {}
    baseline_cost = baseline["cost"] if baseline else {}

    lines += ["## Quality (higher is better)", "", "| Metric | Value | Baseline | Delta |", "|---|---|---|---|"]
    for name, value in sorted(payload["quality"].items()):
        lines.append(_metric_row(name, value, baseline_quality.get(name)))
    lines.append("")

    lines += ["## Cost / latency (lower is better)", "", "| Metric | Value | Baseline | Delta |", "|---|---|---|---|"]
    for name, value in sorted(payload["cost"].items()):
        lines.append(_metric_row(name, value, baseline_cost.get(name)))
    lines.append("")
    lines.append(
        f"`avg_cost_usd` measured for {payload['cost_measured_count']}/{payload['total_cases']} "
        "cases — a run where this is 0 means cost was never observed (not that it was zero)."
    )
    lines.append("")

    return "\n".join(lines)


def _metric_row(name: str, value: float, baseline_value: float | None) -> str:
    if baseline_value is None:
        return f"| {name} | {value:.4f} | — | — |"
    delta = value - baseline_value
    return f"| {name} | {value:.4f} | {baseline_value:.4f} | {delta:+.4f} |"
