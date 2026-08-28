"""Unit tests for the documentation consistency gate."""

from __future__ import annotations

from pathlib import Path

from scripts.check_docs import _check_observability_consistency

ALERTS = """\
groups:
  - name: test
    rules:
      - alert: MRAGHighP95LatencyAnswer
        expr: histogram_quantile(0.95, metric) > 5000
        annotations:
          runbook_url: docs/observability/runbooks.md#mrag-high-latency
      - alert: MRAGHighP95LatencyRetrieve
        expr: histogram_quantile(0.95, metric) > 1000
        annotations:
          runbook_url: docs/observability/runbooks.md#mrag-high-latency
      - alert: MRAGCostBudgetExceeded
        expr: sum(rate(mrag_generation_cost_usd_total[1h])) * 86400 > 100
        annotations:
          runbook_url: docs/observability/runbooks.md#mrag-cost-budget
"""

SLO = """\
- **Alert:** `MRAGHighP95LatencyAnswer` and `MRAGHighP95LatencyRetrieve`.
- **Metric:** `sum(rate(mrag_generation_cost_usd_total[1h])) * 86400`.
- **Alert:** `MRAGCostBudgetExceeded`.
"""

RUNBOOKS = """\
## mrag-high-latency

**Alert:** `MRAGHighP95LatencyAnswer` and `MRAGHighP95LatencyRetrieve`.

## mrag-cost-budget

**Alert:** `MRAGCostBudgetExceeded`.
"""


def _write_fixture(
    tmp_path: Path, *, alerts: str = ALERTS, slo: str = SLO, runbooks: str = RUNBOOKS
) -> tuple[Path, Path, Path]:
    alerts_path = tmp_path / "alerts.yaml"
    slo_path = tmp_path / "slo.md"
    runbooks_path = tmp_path / "runbooks.md"
    alerts_path.write_text(alerts, encoding="utf-8")
    slo_path.write_text(slo, encoding="utf-8")
    runbooks_path.write_text(runbooks, encoding="utf-8")
    return alerts_path, slo_path, runbooks_path


def test_observability_documents_are_consistent() -> None:
    root = Path(__file__).resolve().parents[3]

    assert _check_observability_consistency(
        root / "docs/observability/alerts.yaml",
        root / "docs/observability/slo.md",
        root / "docs/observability/runbooks.md",
    ) == []


def test_reports_a_stale_alert_name(tmp_path: Path) -> None:
    paths = _write_fixture(
        tmp_path, slo=SLO.replace("MRAGHighP95LatencyAnswer", "MRAGHighP95Latency")
    )

    findings = _check_observability_consistency(*paths)

    assert any("MRAGHighP95Latency is not active" in finding.message for finding in findings)


def test_reports_a_missing_runbook_anchor(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path, runbooks=RUNBOOKS.replace("## mrag-cost-budget", "## other"))

    findings = _check_observability_consistency(*paths)

    assert any("missing runbook anchor" in finding.message for finding in findings)


def test_reports_a_cost_projection_mismatch(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path, slo=SLO.replace("* 86400", "* 24"))

    findings = _check_observability_consistency(*paths)

    assert any("cost projection multiplier differs" in finding.message for finding in findings)
