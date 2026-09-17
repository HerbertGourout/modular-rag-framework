"""Check documentation for dangling links, dead APIs, blueprint labels, and cross-doc drift.

This script is intentionally lightweight, mirroring `scripts/check_layering.py`'s style: no
new dependency beyond the project's core PyYAML requirement, with a non-zero exit on findings.

1. Relative links: every `[text](path)` markdown link whose target is a relative filesystem
   path (not `http(s)://`, not a bare `#anchor`) must resolve to a real file, optionally followed
   by a `#fragment` that is not itself checked. `docs/archive/` and `docs/refactoring/` are
   skipped — they are frozen, point-in-time snapshots by design (see `docs/archive/README.md`);
   a link inside one going stale as the target moves or is deleted afterward is expected, not a
   regression, and is not "fixed" by editing archived content.
2. Forbidden terms: names of APIs/files deleted or never built during the ADR-0005 (Lot 17) and
   ADR-0007 (Étapes 1-11) passes must not appear outside `docs/archive/` and `docs/refactoring/`
   (both are point-in-time historical records, not active guidance, and are expected to still
   name deleted things when explaining what was deleted). Active docs legitimately mention these
   same names too — to explain, in past tense, that they were removed and why — so hits are
   checked against `.claude/docs-terms-baseline.txt` (same accepted-baseline pattern as
   `scripts/check_layering.py`): baseline hits are muted by default and only a *new*,
   unexplained mention fails the check; `--strict` shows everything, baseline included.
3. Blueprint labeling: every file under `manifests/blueprints/` must contain the literal string
   "BLUEPRINT" near its top (self-identifies as non-Runnable); no file under `manifests/presets/`
   may contain it (a preset that says BLUEPRINT is either mislabeled or misplaced).
4. Observability consistency: active alert names, runbook anchors, SLO references, and the cost
   projection formula must agree across `alerts.yaml`, `slo.md`, and `runbooks.md`.
5. Style warnings (non-blocking): deterministic layout checks derived from
   `docs/guides/documentation-style-guide.md` — merged metadata lines, missing or repeated `#`
   titles, skipped heading levels, dead same-document anchors, tables not
   separated by blank lines, dense table cells, long paragraphs, long prose lines, and `<br>`
   tags. They never change the exit code: a summary is printed, and `--style-report` lists every
   warning. Judgment-based rules of the guide (idea per paragraph, section roles) stay with the
   `/review-documentation-quality` skill.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / ".claude" / "docs-terms-baseline.txt"

# Directories whose *.md content is a deliberate historical snapshot — old/dead names are
# expected to appear here while explaining what was removed and why.
HISTORICAL_DIRS = {
    PROJECT_ROOT / "docs" / "archive",
    PROJECT_ROOT / "docs" / "refactoring",
}

# Directories not worth walking at all (generated, vendored, or version-controlled but not prose).
SKIP_DIRS = {
    PROJECT_ROOT / ".git",
    # Local review handoffs/reports are workflow state, not active product documentation. They
    # intentionally quote stale or rejected claims while reviewing them and are gitignored.
    PROJECT_ROOT / ".review",
    PROJECT_ROOT / "node_modules",
    PROJECT_ROOT / ".venv",
}

LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
INLINE_CODE_PATTERN = re.compile(r"`[^`]*`")
FENCE_PATTERN = re.compile(r"^\s*```")
ALERT_REFERENCE_PATTERN = re.compile(r"\bMRAG[A-Za-z0-9]+\b")
COST_MULTIPLIER_PATTERN = re.compile(r"\*\s*(\d+(?:\.\d+)?)")

# Dead/never-built API and file names, confirmed against the real codebase during the ADR-0005
# (Lot 17 prototype retirement) and ADR-0007 (layer-boundary stabilization) passes. Extend this
# list when a future deletion pass retires more names. Deliberately excludes names that are
# merely illustrative in generic pattern-teaching examples unrelated to an actual deletion
# (e.g. a hypothetical "RetrieverV2" used to demonstrate Protocol evolution).
FORBIDDEN_TERMS = [
    "QueryRouter",
    "FlowCompiler",
    "HierarchicalCoordinator",
    "WorkflowOrchestrator",
    "team_coordinator",
    "agentic_workflows.md",
    "native five-agent runtime",
    "MRAG_OPENAI_API_KEY",
    "_default_factories.py",
    "ComponentRegistry.default()",
    "three decisions already settled",
    "only `local-hybrid-rag.yaml` actually wires",
    "Settings.log_level` field exists",
]

# The self-identifying header line every blueprint manifest must carry, e.g.
# "# Status: BLUEPRINT — design sketch only, ...". Anchored so prose that merely *mentions* the
# word "BLUEPRINT" (explaining a manifest's history) doesn't trip the preset-side check.
BLUEPRINT_MARKER = "Status: BLUEPRINT"

# Style warnings (check 5). Thresholds are deliberately looser than the style guide's targets
# ("about 100 characters", "two to four sentences") so that only clear outliers are reported.
STYLE_GUIDE_PATH = "docs/guides/documentation-style-guide.md"
MAX_PROSE_LINE_CHARS = 120
MAX_PARAGRAPH_LINES = 10
MAX_TABLE_CELL_CHARS = 200
METADATA_FIELD_PATTERN = re.compile(r"^\*\*[^*\n]{1,60}:\*\*")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_OPEN_PATTERN = re.compile(r"^\s*(```|~~~)")
LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
TABLE_DELIMITER_CELL_PATTERN = re.compile(r"^:?-+:?$")
ANCHOR_LINK_PATTERN = re.compile(r"\]\(#([^)\s]+)\)")
HTML_ID_PATTERN = re.compile(r"""\bid=["']([^"']+)["']""")
BR_TAG_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
THEMATIC_BREAK_PATTERN = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
MARKDOWN_LINK_TEXT_PATTERN = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# A sentence boundary inside a table cell: end punctuation, whitespace, then a capital letter.
# Common abbreviations are masked first so "e.g. Foo" or "vs. Bar" do not count.
SENTENCE_BOUNDARY_PATTERN = re.compile(r"[.!?]\s+[A-Z]")
ABBREVIATION_PATTERN = re.compile(r"\b(?:e\.g|i\.e|vs|etc|cf|approx)\.", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str
    baseline_key: str | None = None

    def render(self) -> str:
        rel_path = self.path.relative_to(PROJECT_ROOT).as_posix()
        return f"{rel_path}:{self.line}: {self.message}"


@dataclass(frozen=True)
class StyleWarning:
    """A non-blocking layout warning; ``rule`` is a stable identifier used for summaries."""

    line: int
    rule: str
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Modular RAG documentation.")
    parser.add_argument(
        "--skip-links",
        action="store_true",
        help="Skip the relative-link resolution check.",
    )
    parser.add_argument(
        "--skip-terms",
        action="store_true",
        help="Skip the forbidden-term check.",
    )
    parser.add_argument(
        "--skip-blueprints",
        action="store_true",
        help="Skip the blueprint-labeling check.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on all forbidden-term findings, including entries listed in the baseline.",
    )
    parser.add_argument(
        "--show-baseline",
        action="store_true",
        help="Print baseline forbidden-term findings even when they are accepted.",
    )
    parser.add_argument(
        "--skip-style",
        action="store_true",
        help="Skip the non-blocking style warnings.",
    )
    parser.add_argument(
        "--style-report",
        action="store_true",
        help="List every style warning instead of only the per-rule summary.",
    )
    parser.add_argument(
        "--style-path",
        action="append",
        default=[],
        metavar="PATH",
        help="Limit style warnings to this Markdown file (repeatable). Implies --style-report.",
    )
    args = parser.parse_args()

    non_term_findings: list[Finding] = []
    md_files = sorted(_iter_markdown_files())

    if not args.skip_links:
        for path in md_files:
            if _is_historical(path):
                continue
            non_term_findings.extend(_check_links(path))

    if not args.skip_blueprints:
        non_term_findings.extend(_check_blueprint_labeling())

    non_term_findings.extend(_check_observability_consistency())

    term_findings: list[Finding] = []
    if not args.skip_terms:
        for path in md_files:
            if _is_historical(path):
                continue
            term_findings.extend(_check_forbidden_terms(path))

    baseline = _load_baseline()
    active_terms = term_findings if args.strict else [
        f for f in term_findings if f.baseline_key not in baseline
    ]
    baseline_terms = [] if args.strict else [
        f for f in term_findings if f.baseline_key in baseline
    ]

    findings = non_term_findings + active_terms

    if not findings:
        print(f"Docs check passed. ({len(md_files)} markdown files scanned)")
        if baseline_terms:
            print(f"Accepted baseline forbidden-term mentions: {len(baseline_terms)}")
            if args.show_baseline:
                for finding in baseline_terms:
                    print(finding.render())
        if not args.skip_style:
            _print_style_warnings(md_files, args.style_path, args.style_report)
        return 0

    print("Documentation issues found:")
    for finding in findings:
        print(finding.render())
    if baseline_terms and not args.strict:
        print(f"\nAccepted baseline forbidden-term mentions not shown: {len(baseline_terms)}")
    print(f"\n{len(findings)} issue(s) across {len(md_files)} markdown files scanned.")
    if not args.skip_style:
        _print_style_warnings(md_files, args.style_path, args.style_report)
    return 1


def _print_style_warnings(md_files: list[Path], style_paths: list[str], report: bool) -> None:
    """Print style warnings. Never affects the exit code (check 5 is advisory only)."""
    if style_paths:
        targets = [Path(raw).resolve() for raw in style_paths]
        report = True
    else:
        targets = [path for path in md_files if not _is_historical(path)]

    per_file: list[tuple[Path, list[StyleWarning]]] = []
    for path in targets:
        if not path.is_file():
            print(f"Style warnings: skipped missing path {path}")
            continue
        warnings = _check_style_text(path.read_text(encoding="utf-8"))
        if warnings:
            per_file.append((path, warnings))

    total = sum(len(warnings) for _, warnings in per_file)
    if total == 0:
        print("Style warnings (non-blocking): none.")
        return

    counts: dict[str, int] = {}
    for _, warnings in per_file:
        for warning in warnings:
            counts[warning.rule] = counts.get(warning.rule, 0) + 1
    summary = ", ".join(f"{rule} {count}" for rule, count in sorted(counts.items()))
    print(
        f"Style warnings (non-blocking, see {STYLE_GUIDE_PATH}): {total} in "
        f"{len(per_file)} file(s): {summary}."
    )
    if not report:
        print("Run with --style-report to list them, or --style-path <file> for one document.")
        return
    for path, warnings in per_file:
        display = _display_path(path)
        for warning in warnings:
            print(f"{display}:{warning.line}: [{warning.rule}] {warning.message}")


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _check_style_text(text: str) -> list[StyleWarning]:
    """Return deterministic layout warnings for one Markdown document.

    Fenced code blocks are ignored. Each rule maps to a section of the documentation style guide.
    """
    warnings: list[StyleWarning] = []
    lines = text.splitlines()
    first_content_line = _skip_front_matter(lines)
    table_lines = _table_line_numbers(lines, first_content_line)

    headings: list[tuple[int, int, str]] = []  # (line number, level, text)
    explicit_ids: set[str] = set()
    anchor_links: list[tuple[int, str]] = []

    in_fence = False
    fence_marker = ""
    previous_kind = "blank"  # blank | heading | table | list | prose | fence
    paragraph_start = 0
    paragraph_lines = 0
    paragraph_fields = 0
    previous_hard_break = False

    def close_paragraph() -> None:
        nonlocal paragraph_lines, paragraph_fields
        if paragraph_lines > MAX_PARAGRAPH_LINES:
            warnings.append(
                StyleWarning(
                    paragraph_start,
                    "long-paragraph",
                    f"paragraph spans {paragraph_lines} source lines (guide section 3.1)",
                )
            )
        paragraph_lines = 0
        paragraph_fields = 0

    for lineno, line in enumerate(lines, start=1):
        if lineno < first_content_line:
            continue
        fence_match = FENCE_OPEN_PATTERN.match(line)
        if in_fence:
            if fence_match and fence_match.group(1) == fence_marker:
                in_fence = False
                previous_kind = "fence"
            continue
        if fence_match:
            close_paragraph()
            in_fence = True
            fence_marker = fence_match.group(1)
            continue

        stripped = line.strip()
        explicit_ids.update(HTML_ID_PATTERN.findall(line))
        anchor_links.extend(
            (lineno, anchor) for anchor in ANCHOR_LINK_PATTERN.findall(_mask_code(line))
        )
        if BR_TAG_PATTERN.search(_mask_code(line)):
            warnings.append(StyleWarning(lineno, "br-tag", "<br> tag (guide section 3.6)"))

        if not stripped or THEMATIC_BREAK_PATTERN.match(stripped):
            close_paragraph()
            previous_kind = "blank"
            continue

        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            close_paragraph()
            headings.append((lineno, len(heading_match.group(1)), heading_match.group(2)))
            previous_kind = "heading"
            continue

        if lineno in table_lines or stripped.startswith("|"):
            close_paragraph()
            if previous_kind in ("prose", "list"):
                warnings.append(
                    StyleWarning(
                        lineno,
                        "table-spacing",
                        "table not preceded by a blank line (guide section 3.4)",
                    )
                )
            if not _is_delimiter_row(stripped):
                _check_table_row(lineno, stripped, warnings)
            previous_kind = "table"
            continue

        if previous_kind == "table":
            warnings.append(
                StyleWarning(
                    lineno, "table-spacing", "text directly after a table row (guide section 3.4)"
                )
            )

        if LIST_ITEM_PATTERN.match(line) or (previous_kind == "list" and line[:1].isspace()):
            close_paragraph()
            previous_kind = "list"
            _check_line_length(lineno, line, warnings)
            continue

        # Prose line (a paragraph, or a lazy continuation of one).
        if previous_kind != "prose":
            paragraph_start = lineno
            previous_hard_break = False
        paragraph_lines += 1
        if METADATA_FIELD_PATTERN.match(stripped):
            # A field after a Markdown hard break (two trailing spaces or a backslash) renders on
            # its own line, so it does not count towards a merged block.
            paragraph_fields = 1 if previous_hard_break else paragraph_fields + 1
            if paragraph_fields == 2:
                warnings.append(
                    StyleWarning(
                        lineno,
                        "merged-metadata",
                        "consecutive **Field:** lines render as one paragraph (guide section 3.3)",
                    )
                )
        _check_line_length(lineno, line, warnings)
        previous_hard_break = line.endswith(("  ", "\\"))
        previous_kind = "prose"

    close_paragraph()
    warnings.extend(_check_headings(headings))

    slugs = _heading_slugs(headings) | explicit_ids
    for lineno, anchor in anchor_links:
        if anchor.lower() not in slugs:
            warnings.append(
                StyleWarning(lineno, "dead-anchor", f"no heading matches #{anchor} (guide section 3.5)")
            )

    return sorted(warnings, key=lambda warning: (warning.line, warning.rule))


def _table_line_numbers(lines: list[str], first_content_line: int) -> set[int]:
    """Line numbers belonging to a GFM table, with or without outer pipes.

    A table is a header row followed by a delimiter row with the same number of cells (as GFM
    requires); it continues while lines are non-blank and still contain a pipe. Rows written
    `A | B` without leading pipes are valid GFM and are recognized here too.
    """
    table_lines: set[int] = set()
    in_fence = False
    fence_marker = ""
    for index, line in enumerate(lines):
        lineno = index + 1
        if lineno < first_content_line:
            continue
        fence_match = FENCE_OPEN_PATTERN.match(line)
        if in_fence:
            if fence_match and fence_match.group(1) == fence_marker:
                in_fence = False
            continue
        if fence_match:
            in_fence = True
            fence_marker = fence_match.group(1)
            continue
        if lineno in table_lines or not _is_delimiter_row(line.strip()):
            continue
        header = lines[index - 1].strip() if index else ""
        if not header or "|" not in _mask_code(header):
            continue
        if len(_split_row_cells(header)) != len(_split_row_cells(line.strip())):
            continue  # GFM requires the header and delimiter rows to have equal cell counts
        table_lines.add(lineno - 1)
        table_lines.add(lineno)
        for follower_index in range(index + 1, len(lines)):
            follower = lines[follower_index].strip()
            if not follower or "|" not in _mask_code(follower):
                break
            table_lines.add(follower_index + 1)
    return table_lines


def _is_delimiter_row(line: str) -> bool:
    if "|" not in line:
        return False
    cells = _split_row_cells(line)
    return bool(cells) and all(TABLE_DELIMITER_CELL_PATTERN.match(cell) for cell in cells)


def _split_row_cells(row: str) -> list[str]:
    """Split one table row into cells, ignoring escaped pipes and pipes inside inline code."""
    masked = _mask_code(row).replace("\\|", "xx")
    return [cell.strip() for cell in masked.strip().strip("|").split("|")]


def _skip_front_matter(lines: list[str]) -> int:
    """Return the first line number after a leading YAML front-matter block (1 when absent)."""
    if not lines or lines[0].strip() != "---":
        return 1
    for index, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return index + 1
    return 1


def _mask_code(line: str) -> str:
    return INLINE_CODE_PATTERN.sub(lambda match: "x" * len(match.group(0)), line)


def _check_line_length(lineno: int, line: str, warnings: list[StyleWarning]) -> None:
    if len(line) <= MAX_PROSE_LINE_CHARS:
        return
    if "](" in line or "http://" in line or "https://" in line:
        return  # links and URLs are exempt (guide section 3.6)
    if max(len(token) for token in line.split()) > MAX_PROSE_LINE_CHARS // 2:
        return  # a long path or identifier cannot be wrapped
    warnings.append(
        StyleWarning(
            lineno,
            "long-line",
            f"prose line of {len(line)} characters (guide section 3.6)",
        )
    )


def _check_table_row(lineno: int, row: str, warnings: list[StyleWarning]) -> None:
    for cell in _split_row_cells(row):
        prose = ABBREVIATION_PATTERN.sub("abbr", cell)
        if len(cell) > MAX_TABLE_CELL_CHARS or SENTENCE_BOUNDARY_PATTERN.search(prose):
            warnings.append(
                StyleWarning(
                    lineno,
                    "dense-table-cell",
                    "table cell holds more than one sentence or a long list (guide section 3.4)",
                )
            )
            return


def _check_headings(headings: list[tuple[int, int, str]]) -> list[StyleWarning]:
    warnings: list[StyleWarning] = []
    titles = [heading for heading in headings if heading[1] == 1]
    if not headings or headings[0][1] != 1:
        warnings.append(
            StyleWarning(
                headings[0][0] if headings else 1,
                "missing-title",
                "document does not start with a single # title (guide section 3.5)",
            )
        )
    for lineno, _level, _text in titles[1:]:
        warnings.append(
            StyleWarning(lineno, "multiple-titles", "more than one # title (guide section 3.5)")
        )

    previous_level = 0
    for lineno, level, _text in headings:
        if previous_level and level > previous_level + 1:
            warnings.append(
                StyleWarning(
                    lineno,
                    "heading-skip",
                    f"heading level jumps from {previous_level} to {level} (guide section 3.5)",
                )
            )
        previous_level = level
    return warnings


def _heading_slugs(headings: list[tuple[int, int, str]]) -> set[str]:
    """GitHub-style anchors, including the -1, -2 suffixes given to repeated headings.

    Each anchor is allocated against every anchor already taken, so a heading literally named
    "Topic-1" occupies `#topic-1` and a later repeat of "Topic" becomes `#topic-2`.
    """
    slugs: set[str] = set()
    for _lineno, _level, text in headings:
        base = _slugify(text)
        candidate = base
        suffix = 0
        while candidate in slugs:
            suffix += 1
            candidate = f"{base}-{suffix}"
        slugs.add(candidate)
    return slugs


def _slugify(text: str) -> str:
    text = MARKDOWN_LINK_TEXT_PATTERN.sub(r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _iter_markdown_files() -> list[Path]:
    files = []
    for path in PROJECT_ROOT.rglob("*.md"):
        if any(skip in path.parents for skip in SKIP_DIRS):
            continue
        relative_parts = path.relative_to(PROJECT_ROOT).parts
        if any(part.startswith((".pytest-", ".check-tmp")) for part in relative_parts):
            continue
        files.append(path)
    return files


def _is_historical(path: Path) -> bool:
    return any(historical in path.parents for historical in HISTORICAL_DIRS)


def _load_baseline() -> set[str]:
    if not BASELINE_PATH.exists():
        return set()
    return {
        line.strip()
        for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _check_links(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8")
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Strip inline code spans first: a regex/code snippet like `\b0[1-9](?:...)`  reads as a
        # markdown link (`[...](...)`) to the same naive pattern otherwise.
        prose = INLINE_CODE_PATTERN.sub("", line)
        for match in LINK_PATTERN.finditer(prose):
            target = match.group(1)
            resolved = _resolve_link_target(path, target)
            if resolved is None:
                continue
            if not resolved.exists():
                findings.append(
                    Finding(path=path, line=lineno, message=f"broken relative link: {target}")
                )
    return findings


def _resolve_link_target(source: Path, target: str) -> Path | None:
    if not target or target.startswith(("http://", "https://", "mailto:", "#")):
        return None
    # Strip a trailing #fragment; fragments aren't validated (would require heading parsing).
    target_path = target.split("#", 1)[0]
    if not target_path:
        return None
    if target_path.startswith("/"):
        return None  # absolute paths outside the repo aren't this script's concern
    return (source.parent / target_path).resolve()


def _check_forbidden_terms(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    rel_path = path.relative_to(PROJECT_ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        for term in FORBIDDEN_TERMS:
            if term in line:
                findings.append(
                    Finding(
                        path=path,
                        line=lineno,
                        message=(
                            f'forbidden term "{term}" '
                            "(dead/never-built API, see script docstring)"
                        ),
                        baseline_key=f"{rel_path}|{term}",
                    )
                )
    return findings


def _check_blueprint_labeling() -> list[Finding]:
    findings: list[Finding] = []

    blueprints_dir = PROJECT_ROOT / "manifests" / "blueprints"
    if blueprints_dir.exists():
        for path in sorted(blueprints_dir.glob("*.yaml")):
            text = path.read_text(encoding="utf-8")
            if BLUEPRINT_MARKER not in text:
                findings.append(
                    Finding(
                        path=path,
                        line=1,
                        message="blueprint manifest missing a 'BLUEPRINT' self-identifying marker",
                    )
                )

    presets_dir = PROJECT_ROOT / "manifests" / "presets"
    if presets_dir.exists():
        for path in sorted(presets_dir.glob("*.yaml")):
            text = path.read_text(encoding="utf-8")
            if BLUEPRINT_MARKER in text:
                findings.append(
                    Finding(
                        path=path,
                        line=1,
                        message=(
                            "preset manifest contains 'BLUEPRINT' marker — "
                            "mislabeled or misplaced"
                        ),
                    )
                )

    return findings


def _check_observability_consistency(
    alerts_path: Path | None = None,
    slo_path: Path | None = None,
    runbooks_path: Path | None = None,
) -> list[Finding]:
    """Fail closed on references shared by the alert, SLO, and runbook artifacts.

    These checks deliberately cover objective relationships only. They do not try to generate or
    judge narrative documentation, but they prevent a renamed rule or corrected PromQL formula
    from being updated in one artifact and silently left stale in another.
    """
    alerts_path = alerts_path or PROJECT_ROOT / "docs" / "observability" / "alerts.yaml"
    slo_path = slo_path or PROJECT_ROOT / "docs" / "observability" / "slo.md"
    runbooks_path = runbooks_path or PROJECT_ROOT / "docs" / "observability" / "runbooks.md"
    paths = (alerts_path, slo_path, runbooks_path)
    if not any(path.exists() for path in paths):
        return []
    missing = [path for path in paths if not path.exists()]
    if missing:
        return [
            Finding(path=path, line=1, message="required observability document is missing")
            for path in missing
        ]

    findings: list[Finding] = []
    try:
        parsed = yaml.safe_load(alerts_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [Finding(path=alerts_path, line=1, message=f"invalid alerts YAML: {exc}")]

    try:
        rules = [rule for group in parsed["groups"] for rule in group["rules"]]
        rules_by_name = {str(rule["alert"]): rule for rule in rules}
    except (KeyError, TypeError):
        return [
            Finding(
                path=alerts_path,
                line=1,
                message="alerts YAML must contain groups[].rules[] entries with alert names",
            )
        ]

    runbook_lines = runbooks_path.read_text(encoding="utf-8").splitlines()
    slo_lines = slo_path.read_text(encoding="utf-8").splitlines()
    runbook_headings = {
        line.removeprefix("## ").strip().lower()
        for line in runbook_lines
        if line.startswith("## ")
    }

    for rule_name, rule in rules_by_name.items():
        annotations = rule.get("annotations") or {}
        runbook_url = annotations.get("runbook_url") if isinstance(annotations, dict) else None
        if not isinstance(runbook_url, str) or "#" not in runbook_url:
            findings.append(
                Finding(
                    path=alerts_path,
                    line=_line_number(alerts_path, f"alert: {rule_name}"),
                    message=f"alert {rule_name} has no anchored runbook_url",
                )
            )
            continue
        target, anchor = runbook_url.split("#", 1)
        if target != "docs/observability/runbooks.md" or anchor.lower() not in runbook_headings:
            findings.append(
                Finding(
                    path=alerts_path,
                    line=_line_number(alerts_path, f"alert: {rule_name}"),
                    message=f"alert {rule_name} points to a missing runbook anchor: {runbook_url}",
                )
            )

    documented_runbook_alerts = _documented_alert_references(runbook_lines)
    for rule_name in sorted(rules_by_name.keys() - documented_runbook_alerts):
        findings.append(
            Finding(
                path=runbooks_path,
                line=1,
                message=f"active alert {rule_name} is not named in an '**Alert:**' entry",
            )
        )

    for path, lines in ((slo_path, slo_lines), (runbooks_path, runbook_lines)):
        for line_number, line in enumerate(lines, start=1):
            if "**Alert:**" not in line:
                continue
            for reference in ALERT_REFERENCE_PATTERN.findall(line):
                if reference not in rules_by_name:
                    findings.append(
                        Finding(
                            path=path,
                            line=line_number,
                            message=f"documented alert {reference} is not active in alerts.yaml",
                        )
                    )

    cost_rule = rules_by_name.get("MRAGCostBudgetExceeded")
    if cost_rule is not None:
        alert_multiplier = _cost_multiplier(str(cost_rule.get("expr", "")))
        for line_number, line in enumerate(slo_lines, start=1):
            if "mrag_generation_cost_usd_total" not in line or "rate(" not in line:
                continue
            slo_multiplier = _cost_multiplier(line)
            if alert_multiplier is None or slo_multiplier != alert_multiplier:
                findings.append(
                    Finding(
                        path=slo_path,
                        line=line_number,
                        message=(
                            "cost projection multiplier differs from "
                            f"MRAGCostBudgetExceeded ({slo_multiplier!r} != {alert_multiplier!r})"
                        ),
                    )
                )
    return findings


def _documented_alert_references(lines: list[str]) -> set[str]:
    return {
        reference
        for line in lines
        if "**Alert:**" in line
        for reference in ALERT_REFERENCE_PATTERN.findall(line)
    }


def _cost_multiplier(expression: str) -> float | None:
    match = COST_MULTIPLIER_PATTERN.search(expression)
    return float(match.group(1)) if match else None


def _line_number(path: Path, needle: str) -> int:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            return line_number
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
