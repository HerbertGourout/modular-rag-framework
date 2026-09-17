"""Unit tests for the documentation consistency gate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from scripts import check_docs
from scripts.check_docs import (
    MAX_PARAGRAPH_LINES,
    MAX_PROSE_LINE_CHARS,
    _check_observability_consistency,
    _check_style_text,
)

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


# --- Style warnings (check 5) -------------------------------------------------------------------


def _rules(text: str) -> list[tuple[int, str]]:
    return [(warning.line, warning.rule) for warning in _check_style_text(text)]


def test_clean_document_has_no_style_warnings() -> None:
    text = """\
# Title

- **Date:** 2026-09-17
- **Status:** Active

## Section

A short paragraph.

| Name | Value |
|---|---|
| a | b |

See [the section](#section).
"""
    assert _rules(text) == []


def test_reports_merged_metadata_lines() -> None:
    text = "# Title\n\n**Date:** 2026-09-17\n**Batch:** 0\n"

    assert _rules(text) == [(4, "merged-metadata")]


def test_metadata_after_a_hard_break_is_not_merged() -> None:
    text = "# Title\n\n**Date:** 2026-09-17  \n**Batch:** 0\\\n**Scope:** docs\n"

    assert _rules(text) == []


def test_ignores_fenced_code_and_front_matter() -> None:
    text = (
        "---\n"
        f"description: {'x ' * MAX_PROSE_LINE_CHARS}\n"
        "---\n"
        "# Title\n\n"
        "```markdown\n**Date:** 1\n**Batch:** 0\n<br>\n```\n"
    )

    assert _rules(text) == []


def test_reports_missing_and_repeated_titles() -> None:
    assert _rules("## Only a section\n") == [(1, "missing-title")]
    assert _rules("# One\n\n# Two\n") == [(3, "multiple-titles")]


def test_reports_skipped_heading_level() -> None:
    assert _rules("# Title\n\n### Too deep\n") == [(3, "heading-skip")]


def test_reports_dead_anchor_but_accepts_suffixes_and_html_ids() -> None:
    text = """\
# Title

## Notes

## Notes

<a id="kept-anchor"></a>

[a](#notes) [b](#notes-1) [c](#kept-anchor) [d](#missing)
"""
    assert _rules(text) == [(9, "dead-anchor")]


def test_anchor_slug_drops_punctuation_like_github() -> None:
    text = "# Title\n\n## 3.8 A — two overviews\n\n[x](#38-a--two-overviews)\n"

    assert _rules(text) == []


def test_reports_table_spacing_on_both_sides() -> None:
    text = "# Title\n\nIntro line\n| a | b |\n|---|---|\n| 1 | 2 |\nTrailing prose\n"

    assert _rules(text) == [(4, "table-spacing"), (7, "table-spacing")]


def test_table_without_outer_pipes_is_checked_like_a_piped_table() -> None:
    text = "# Title\n\nIntro\nA | B\n--- | ---\nx | First sentence. Second sentence.\nAfter\n"

    assert _rules(text) == [
        (4, "table-spacing"),
        (6, "dense-table-cell"),
        (7, "table-spacing"),
    ]


def test_a_pipe_in_prose_or_inline_code_is_not_a_table() -> None:
    assert _rules("# Title\n\nUse `a | b` in a filter.\n") == []
    assert _rules("# Title\n\nchoose A | B when unsure\n") == []


def test_header_and_delimiter_rows_must_have_the_same_cell_count() -> None:
    # GFM only recognizes a table when both rows have equal widths, so prose shaped like a table
    # must not be checked as one.
    mismatched = "# Title\n\nA | B | C\n--- | ---\nx | First sentence. Second sentence.\n"
    piped_match = "# Title\n\n| A | B |\n|---|---|\n| x | First sentence. Second sentence. |\n"
    # Rows written with outer pipes are authored as a table; they stay checked even when the
    # widths disagree, which is how a malformed table (audit finding F3) is still reported.
    piped_mismatch = "# Title\n\n| A | B | C |\n|---|---|\n| x | First sentence. Second one. |\n"

    assert _rules(mismatched) == []
    assert _rules(piped_match) == [(5, "dense-table-cell")]
    assert _rules(piped_mismatch) == [(5, "dense-table-cell")]


def test_slug_allocation_skips_a_suffix_taken_by_another_heading() -> None:
    # "Topic-1" already owns #topic-1, so the repeated "Topic" falls through to #topic-2.
    literal_suffix_first = "# Title\n\n## Topic\n\n## Topic-1\n\n## Topic\n\n[x](#topic-2)\n"
    # Reversed: the repeat takes #topic-1, and the literal "Topic-1" falls through to #topic-1-1.
    repeat_first = "# Title\n\n## Topic\n\n## Topic\n\n## Topic-1\n\n[a](#topic-1) [b](#topic-1-1)\n"

    assert _rules(literal_suffix_first) == []
    assert _rules(repeat_first) == []


def test_reports_multi_sentence_table_cell_but_not_abbreviations() -> None:
    dense = "# Title\n\n| a | b |\n|---|---|\n| x | First sentence. Second sentence. |\n"
    abbreviated = "# Title\n\n| a | b |\n|---|---|\n| x | Native vs. Delegated, e.g. Lot 22 |\n"

    assert _rules(dense) == [(5, "dense-table-cell")]
    assert _rules(abbreviated) == []


def test_reports_long_paragraph() -> None:
    body = "\n".join("words" for _ in range(MAX_PARAGRAPH_LINES + 1))

    assert _rules(f"# Title\n\n{body}\n") == [(3, "long-paragraph")]


def test_reports_long_prose_line_but_exempts_links_and_unbreakable_tokens() -> None:
    long_prose = "word " * (MAX_PROSE_LINE_CHARS // 4)
    long_link = f"[{'word ' * 30}](other.md)"
    long_path = "`" + "a/" * (MAX_PROSE_LINE_CHARS // 2) + "`"

    assert _rules(f"# Title\n\n{long_prose}\n") == [(3, "long-line")]
    assert _rules(f"# Title\n\n{long_link}\n") == []
    assert _rules(f"# Title\n\n{long_path}\n") == []


def test_reports_br_tag_outside_inline_code() -> None:
    assert _rules("# Title\n\nOne<br>two\n") == [(3, "br-tag")]
    assert _rules("# Title\n\nUse `<br>` sparingly\n") == []


# --- CLI and exit-code contract ------------------------------------------------------------------

WARNING_DOCUMENT = "# Title\n\n**Date:** 2026-09-17\n**Batch:** 0\n"


def _run_cli(
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    blocking: list[check_docs.Finding] | None = None,
    md_files: list[Path] | None = None,
) -> int:
    """Run ``main()`` with the repository scan stubbed out, so results stay deterministic."""
    monkeypatch.setattr(sys, "argv", ["check_docs.py", *args])
    monkeypatch.setattr(check_docs, "_check_blueprint_labeling", lambda: list(blocking or []))
    monkeypatch.setattr(check_docs, "_check_observability_consistency", lambda: [])
    monkeypatch.setattr(check_docs, "_check_links", lambda path: [])
    monkeypatch.setattr(check_docs, "_check_forbidden_terms", lambda path: [])
    monkeypatch.setattr(check_docs, "_iter_markdown_files", lambda: list(md_files or []))
    return check_docs.main()


def test_warnings_do_not_change_a_successful_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    document = tmp_path / "warns.md"
    document.write_text(WARNING_DOCUMENT, encoding="utf-8")

    exit_code = _run_cli(monkeypatch, "--style-path", str(document))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "merged-metadata 1" in output
    assert "[merged-metadata]" in output  # --style-path implies the detailed report


def test_warnings_do_not_change_a_blocking_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    document = tmp_path / "warns.md"
    document.write_text(WARNING_DOCUMENT, encoding="utf-8")
    blocking = check_docs.Finding(
        path=check_docs.PROJECT_ROOT / "docs" / "example.md", line=1, message="broken relative link"
    )

    exit_code = _run_cli(monkeypatch, "--style-path", str(document), blocking=[blocking])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "broken relative link" in output
    assert "[merged-metadata]" in output


def test_skip_style_suppresses_every_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    document = tmp_path / "warns.md"
    document.write_text(WARNING_DOCUMENT, encoding="utf-8")

    exit_code = _run_cli(monkeypatch, "--skip-style", "--style-path", str(document))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Style warnings" not in output


def test_summary_only_without_the_report_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    document = tmp_path / "warns.md"
    document.write_text(WARNING_DOCUMENT, encoding="utf-8")

    exit_code = _run_cli(monkeypatch, md_files=[document])
    summary_output = capsys.readouterr().out

    assert exit_code == 0
    assert "Run with --style-report" in summary_output
    assert "[merged-metadata]" not in summary_output

    assert _run_cli(monkeypatch, "--style-report", md_files=[document]) == 0
    assert "[merged-metadata]" in capsys.readouterr().out


def test_repeated_explicit_paths_include_historical_and_missing_files(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    historical = tmp_path / "archive" / "old.md"
    historical.parent.mkdir()
    historical.write_text(WARNING_DOCUMENT, encoding="utf-8")
    monkeypatch.setattr(check_docs, "HISTORICAL_DIRS", {historical.parent})

    exit_code = _run_cli(
        monkeypatch,
        "--style-path",
        str(historical),
        "--style-path",
        str(tmp_path / "absent.md"),
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "skipped missing path" in output
    assert "[merged-metadata]" in output  # an explicit path bypasses the historical exclusion


def test_style_guide_and_documentation_skills_comply_with_the_checks() -> None:
    root = Path(__file__).resolve().parents[3]
    documents = [
        "docs/guides/documentation-style-guide.md",
        ".claude/skills/write-documentation/SKILL.md",
        ".claude/skills/review-documentation-quality/SKILL.md",
        ".claude/skills/verify-documentation-truth/SKILL.md",
    ]

    for document in documents:
        text = (root / document).read_text(encoding="utf-8")
        assert _check_style_text(text) == [], document
