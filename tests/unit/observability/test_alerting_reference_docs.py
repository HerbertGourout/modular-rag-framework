"""Static regression checks for the reference alerting/SLO documents
(docs/observability/alerts.yaml, docs/observability/slo.md) — ADR-0013,
Lot 12 (external plan — "Metrics, Dashboards, and SLO").

These are plain-text/YAML reference material, not executable config wired
into CI against a live Prometheus, so nothing else in the test suite touches
them. Codex review pass 1 found two real defects here (HIGH-004, MEDIUM-002)
that only a load-bearing test would have caught before they shipped — these
tests exist specifically to keep those two fixed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ALERTS_PATH = REPO_ROOT / "docs" / "observability" / "alerts.yaml"
SLO_PATH = REPO_ROOT / "docs" / "observability" / "slo.md"


def _load_alerts() -> dict[str, Any]:
    return yaml.safe_load(ALERTS_PATH.read_text(encoding="utf-8"))


def _all_rules() -> list[dict[str, Any]]:
    return [rule for group in _load_alerts()["groups"] for rule in group["rules"]]


def _rule(name: str) -> dict[str, Any]:
    rules = {r["alert"]: r for r in _all_rules()}
    assert name in rules, f"expected alert rule {name!r} in alerts.yaml, found {sorted(rules)}"
    return rules[name]


def test_alerts_yaml_parses_as_valid_yaml() -> None:
    parsed = _load_alerts()
    assert "groups" in parsed
    assert len(_all_rules()) > 0


def test_cost_budget_alert_uses_the_seconds_per_day_multiplier() -> None:
    """Codex review pass 1 (HIGH-004): `rate(...[1h])` is a per-*second*
    average rate (PromQL semantics), so projecting it to a full day requires
    multiplying by 86400 (seconds/day), not 24 -- a prior version used
    `* 24`, a 3600x under-count that would only have fired near
    $360,000/day of actual spend against a stated $100/day threshold."""
    expr = _rule("MRAGCostBudgetExceeded")["expr"]

    assert "* 86400" in expr
    assert "* 24" not in expr


def test_latency_alerts_are_split_per_operation_matching_the_slo_targets() -> None:
    """Codex review pass 1 (MEDIUM-002): a single `MRAGHighP95Latency` rule
    applied one scalar 5000ms threshold to both `answer` and `retrieve`, even
    though slo.md sets different targets (answer: 5s, retrieve: 1s) --
    `retrieve` could run 4x over its actual SLO without ever paging. Fixed by
    splitting into one rule per operation, each carrying its own threshold."""
    answer_rule = _rule("MRAGHighP95LatencyAnswer")
    retrieve_rule = _rule("MRAGHighP95LatencyRetrieve")

    assert 'operation="answer"' in answer_rule["expr"]
    assert "> 5000" in answer_rule["expr"]
    assert answer_rule["labels"]["operation"] == "answer"

    assert 'operation="retrieve"' in retrieve_rule["expr"]
    assert "> 1000" in retrieve_rule["expr"]
    assert retrieve_rule["labels"]["operation"] == "retrieve"

    # No stale single-threshold rule left behind covering both operations.
    assert "MRAGHighP95Latency" not in {r["alert"] for r in _all_rules()}


def test_latency_alert_thresholds_match_the_documented_slo_targets() -> None:
    """Cross-check against slo.md's own prose so the two documents cannot
    silently drift apart again -- a looser check than parsing slo.md's
    PromQL (which is embedded in prose, not YAML), but catches the exact
    class of mismatch this finding was about."""
    slo_text = SLO_PATH.read_text(encoding="utf-8")

    assert "`/answer` under 5 seconds" in slo_text
    assert "`/retrieve` under 1\nsecond" in slo_text


def test_every_alert_rule_has_a_runbook_url_pointing_at_runbooks_md() -> None:
    for rule in _all_rules():
        runbook_url = rule["annotations"]["runbook_url"]
        assert runbook_url.startswith("docs/observability/runbooks.md#")
