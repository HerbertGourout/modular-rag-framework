"""Check documentation for dangling links, dead-API references, and blueprint labeling.

This script is intentionally lightweight, mirroring `scripts/check_layering.py`'s style: no
external deps, three independent checks over `*.md` files, non-zero exit on any finding.

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
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

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
    PROJECT_ROOT / "node_modules",
    PROJECT_ROOT / ".venv",
}

LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
INLINE_CODE_PATTERN = re.compile(r"`[^`]*`")
FENCE_PATTERN = re.compile(r"^\s*```")

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
]

# The self-identifying header line every blueprint manifest must carry, e.g.
# "# Status: BLUEPRINT — design sketch only, ...". Anchored so prose that merely *mentions* the
# word "BLUEPRINT" (explaining a manifest's history) doesn't trip the preset-side check.
BLUEPRINT_MARKER = "Status: BLUEPRINT"


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str
    baseline_key: str | None = None

    def render(self) -> str:
        rel_path = self.path.relative_to(PROJECT_ROOT).as_posix()
        return f"{rel_path}:{self.line}: {self.message}"


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
        return 0

    print("Documentation issues found:")
    for finding in findings:
        print(finding.render())
    if baseline_terms and not args.strict:
        print(f"\nAccepted baseline forbidden-term mentions not shown: {len(baseline_terms)}")
    print(f"\n{len(findings)} issue(s) across {len(md_files)} markdown files scanned.")
    return 1


def _iter_markdown_files() -> list[Path]:
    files = []
    for path in PROJECT_ROOT.rglob("*.md"):
        if any(skip in path.parents for skip in SKIP_DIRS):
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
                        message=f'forbidden term "{term}" (dead/never-built API, see script docstring)',
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
                        message="preset manifest contains 'BLUEPRINT' marker — mislabeled or misplaced",
                    )
                )

    return findings


if __name__ == "__main__":
    raise SystemExit(main())
