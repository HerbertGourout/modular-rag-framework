"""Offline benchmark runner (Batch 13, external plan — "Offline benchmark";
not this repo's own docs/refactoring-plan.md Lot numbering, which already
used "Lot 13" for an unrelated, already-completed metric-vocabulary fix).

Loads a golden set (eval/datasets/loader.py), ingests its corpus, runs every
case through a wired `ApplicationService`, and produces a machine-readable
JSON report plus a human-readable Markdown report — comparable across runs
because both are keyed by the current git commit. See
docs/guides/offline-evaluation.md for the full design, the documented
thresholds, and why every number here comes from a deterministic pipeline
with no LLM API key.

Usage:
    python scripts/run_benchmark.py                    # report-only, local
    python scripts/run_benchmark.py --enforce           # blocking mode (CI)
    python scripts/run_benchmark.py --update-baseline   # accept current numbers as the new baseline

Codex review (pass 1, MEDIUM-002; corrected pass 2, HIGH-004): the wired
indexer's collection (`Indexer.clear()` — delete + recreate) is cleared
before ingesting the golden set's corpus, but ONLY when `--manifest` is the
shipped benchmark manifest (recognized by its own `id:` field,
`KNOWN_BENCHMARK_MANIFEST_ID` below) or `--clear-collection` is passed
explicitly. The first corrective pass defaulted to clearing whichever
manifest's collection the caller supplied, with only an opt-*out* flag —
that deletes an arbitrary custom/shared/production collection by default
for anyone running this against their own manifest, which the "works
unchanged" wording below always intended to support. This is now opt-in by
manifest identity: the default benchmark manifest gets a fully reproducible,
clean-state run automatically; any other manifest is left untouched unless
you explicitly pass --clear-collection, having confirmed its collection is
safe to wipe.

Lives outside src/modular_rag/ on purpose: it imports app/orchestration
(manifest loading, wiring) alongside eval/ (offline scoring), which
`eval/`'s own hexagonal-layering rule (domain modules import only
contracts/ + core/models/) forbids from within src/modular_rag/eval/ itself
— see scripts/check_layering.py, which only scans src/modular_rag/.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "src/modular_rag/eval/manifests/benchmark-deterministic.yaml"
DEFAULT_DATASET = PROJECT_ROOT / "src/modular_rag/eval/datasets/core_v1.yaml"
DEFAULT_BASELINE = PROJECT_ROOT / "src/modular_rag/eval/reports/baseline.json"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "src/modular_rag/eval/reports/latest.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "src/modular_rag/eval/reports/latest.md"

# Codex review (pass 2, HIGH-004): the "ownership marker" this script checks
# before auto-clearing a collection — the shipped benchmark manifest's own
# `id:` field (src/modular_rag/eval/manifests/benchmark-deterministic.yaml).
# A manifest with any other id is never assumed to be benchmark-owned.
KNOWN_BENCHMARK_MANIFEST_ID = "eval-benchmark-deterministic"


def _should_clear_collection(manifest_id: str, force_clear: bool) -> bool:
    """The ownership check behind auto-clearing a collection (Codex review
    pass 2, HIGH-004): true only for the recognized benchmark manifest, or
    when the caller explicitly forces it via --clear-collection. Extracted
    as its own function so this safety-critical decision (never destroy an
    arbitrary caller-supplied collection by default) has a direct unit test
    that needs no live Qdrant or manifest wiring."""
    return force_clear or manifest_id == KNOWN_BENCHMARK_MANIFEST_ID


def _git_commit_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return result.stdout.strip() or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--retrieval-k", type=int, default=5)
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.02,
        help="Absolute tolerance before a metric counts as a regression (default: 0.02).",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Run the quality gate in BLOCKING mode: exit 1 on any regression past baseline. "
        "Without this flag the gate runs REPORT_ONLY (always exits 0; violations are printed).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="After running, overwrite --baseline with this run's quality/cost numbers.",
    )
    parser.add_argument(
        "--clear-collection",
        action="store_true",
        help="Force-clear --manifest's indexer collection before ingest (Indexer.clear(): "
        "delete + recreate). DESTRUCTIVE to whatever that collection currently holds -- only "
        "pass this against a manifest/collection you own and know is safe to wipe. The shipped "
        "benchmark manifest clears automatically without this flag (recognized by its own "
        "manifest id); any other --manifest is left untouched unless you pass this explicitly.",
    )
    args = parser.parse_args()

    # Imported here, not at module level: this script's own sys.path is not
    # guaranteed to have `modular_rag` importable until argparse has already
    # validated the CLI invocation (fail fast on a bad flag before paying
    # any import cost) — matching the lazy-import discipline the rest of
    # this codebase applies to heavy dependencies, applied here to the
    # whole package for a lighter reason (fast --help).
    from modular_rag.app.bootstrap import load_application
    from modular_rag.eval.datasets.loader import load_golden_set
    from modular_rag.eval.quality_gate import GateMode, QualityGate, QualityGateError
    from modular_rag.eval.reporting import (
        build_report_payload,
        load_json_report,
        render_markdown_report,
        write_json_report,
    )
    from modular_rag.eval.runners.benchmark import BenchmarkRunner
    from modular_rag.eval.scorers.exact_match import ExactMatchEvaluator

    golden = load_golden_set(args.dataset)
    print(f"Loaded golden set '{golden.name}' (schema {golden.schema_version}): "
          f"{len(golden)} cases, {len(golden.corpus)} corpus chunks.")

    app = load_application(args.manifest)
    try:
        if _should_clear_collection(app.manifest_id, args.clear_collection):
            print(f"Clearing indexer collection before ingest ({app.indexer.name()})...")
            app.indexer.clear()
        else:
            print(
                f"Skipping collection clear for manifest {app.manifest_id!r} (not the "
                f"recognized benchmark manifest, {KNOWN_BENCHMARK_MANIFEST_ID!r}) -- pass "
                "--clear-collection to force a clean-state run against this manifest's own "
                "collection. Without it, a stale point from a prior run may affect this run's "
                "retrieval scoring."
            )
        app.ingest_chunks(golden.corpus)
        runner = BenchmarkRunner(
            engine=app, evaluator=ExactMatchEvaluator(), retrieval_k=args.retrieval_k
        )
        report = runner.run(golden.cases)
    finally:
        app.close()

    payload = build_report_payload(
        report,
        dataset_name=golden.name,
        dataset_schema_version=golden.schema_version,
        manifest_path=args.manifest,
        commit_sha=_git_commit_sha(),
    )

    baseline_payload = load_json_report(args.baseline)
    baseline_for_render = (
        {"quality": baseline_payload["quality"], "cost": baseline_payload["cost"]}
        if baseline_payload
        else None
    )

    markdown = render_markdown_report(payload, baseline=baseline_for_render)
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    write_json_report(payload, args.output_json)
    Path(args.output_md).write_text(markdown, encoding="utf-8")
    print(markdown)

    if args.update_baseline:
        write_json_report(payload, args.baseline)
        print(f"Baseline updated: {args.baseline}")
        return 0

    if baseline_payload is None:
        print(
            f"No baseline found at {args.baseline} — nothing to gate against. "
            "Run with --update-baseline to create one."
        )
        return 0

    quality_baseline = baseline_payload["quality"]
    cost_baseline = baseline_payload["cost"]
    gate = QualityGate(
        {**quality_baseline, **cost_baseline},
        mode=GateMode.BLOCKING if args.enforce else GateMode.REPORT_ONLY,
        tolerance=args.tolerance,
        lower_is_better=frozenset(cost_baseline),
    )

    try:
        result = gate.check({**payload["quality"], **payload["cost"]})
    except QualityGateError as exc:
        print("Quality gate FAILED (blocking mode):")
        for violation in exc.result.violations:
            print(f"  - {violation.metric}: baseline={violation.baseline} actual={violation.actual}")
        return 1

    if not result.passed:
        print("Quality gate reported violations (report-only mode, not blocking):")
        for violation in result.violations:
            print(f"  - {violation.metric}: baseline={violation.baseline} actual={violation.actual}")
    else:
        print("Quality gate passed: no regression past baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
