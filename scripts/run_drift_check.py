"""Offline drift check (Batch 14, external plan — "Feedback, drift, and
human review"; ADR-0014).

Loads a manifest, reads back stored feedback/review-queue/document-lifecycle
state through `ApplicationService`'s public accessors, computes a
`DriftReport` (`eval/drift_detection.py`), and prints it. Per ADR-0008, this
is never manifest-activated — a script, run manually or on a schedule
outside this codebase (which has no scheduler component), the same way
`scripts/run_benchmark.py` is.

Lives outside src/modular_rag/ for the identical layering reason
`scripts/run_benchmark.py` does: it needs `app`/`orchestration` imports
`eval/`'s own hexagonal-layering rule forbids from within
`src/modular_rag/eval/` itself.

Baseline and current snapshots use disjoint, non-overlapping observation
windows (Codex review pass 2, HIGH-001 — reopened): an earlier version
bounded each snapshot to a trailing `--window-days` window measured back
from its own generation time, which still let baseline-era records reappear
in the current window whenever the two runs were close together in time,
diluting a severe recent regression exactly as the original, pre-windowing
bug did. The fix: a baseline's own window is `[now - window_days, now]`,
persisted as explicit `window_start`/`window_end` boundaries (not just a
duration); a later comparison run's current window is
`[baseline_window_end, now]` — starting exactly where the baseline's window
ended, so no record can be counted in both. `--window-days` on a comparison
run instead enforces a minimum elapsed time since the baseline before the
comparison is considered meaningful (too little elapsed time means too
little current data to trust a rate computed from it).

`--window-days` must be a positive integer (Codex review pass 2, MEDIUM-004):
a zero or negative value previously computed a window boundary at or after
"now", so `list_since()` silently returned no current records — a
structurally valid but empty report that could be mistaken for a healthy
one, with no diagnostic and no non-zero exit code.

Usage:
    python scripts/run_drift_check.py --manifest <path>
    python scripts/run_drift_check.py --manifest <path> --update-baseline \
        --baseline drift-baseline.json
    python scripts/run_drift_check.py --manifest <path> --baseline drift-baseline.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

_DEFAULT_WINDOW_DAYS = 7


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Pipeline manifest YAML.")
    parser.add_argument(
        "--baseline",
        default=None,
        help="Path to a previously-written snapshot JSON to compare against. "
        "Without this, only the current snapshot is printed (report-only).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write the current snapshot to --baseline instead of comparing.",
    )
    parser.add_argument(
        "--stale-after-days", type=int, default=90, help="Document freshness threshold (days)."
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=_DEFAULT_WINDOW_DAYS,
        help=(
            "When establishing a baseline (--update-baseline), the trailing window (days) "
            "of feedback it captures. When comparing against an existing baseline, the "
            "minimum elapsed time (days) required since the baseline's own window ended "
            "before the comparison is considered meaningful — the current window always "
            f"starts exactly where the baseline's ended, never overlapping it (default: "
            f"{_DEFAULT_WINDOW_DAYS}). Must be >= 1."
        ),
    )
    args = parser.parse_args()

    if args.window_days < 1:
        print(
            f"--window-days must be >= 1 (got {args.window_days!r}) — a zero or negative "
            "value would silently exclude all current feedback instead of detecting drift."
        )
        return 1

    from modular_rag.app.bootstrap import load_application
    from modular_rag.eval.drift_detection import (
        DocumentFreshnessMetrics,
        DriftSnapshot,
        EscalationMetrics,
        FeedbackDriftMetrics,
        compute_document_freshness,
        compute_drift,
        compute_escalation_metrics,
        compute_feedback_drift_metrics,
    )

    now = datetime.now(UTC)

    # Decide this run's own observation window *before* touching the
    # backing stores. A baseline always gets a fresh trailing window. A
    # comparison run's current window starts exactly at the baseline's own
    # `window_end` — disjoint from it by construction, not merely
    # same-sized — so no record can be double-counted across the two
    # snapshots. A report-only run (no --baseline at all) falls back to a
    # plain trailing window, matching the original simple behavior.
    baseline_payload = None
    if args.update_baseline:
        window_start = now - timedelta(days=args.window_days)
    elif args.baseline:
        baseline_path = Path(args.baseline)
        if not baseline_path.exists():
            print(f"No baseline found at {baseline_path} — nothing to compare against.")
            return 0
        baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        raw_window_end = baseline_payload.get("window_end")
        if raw_window_end is None:
            print(
                f"Baseline at {baseline_path} has no window_end — it predates disjoint-window "
                "support. Regenerate it with --update-baseline before comparing."
            )
            return 1
        baseline_window_end = datetime.fromisoformat(raw_window_end)
        elapsed = now - baseline_window_end
        if elapsed < timedelta(days=args.window_days):
            print(
                f"Only {elapsed} has elapsed since the baseline's window ended "
                f"({baseline_window_end.isoformat()}) — --window-days={args.window_days} "
                "requires at least that long for a meaningful comparison. Wait longer, or "
                "pass a smaller --window-days if a shorter comparison period is acceptable."
            )
            return 1
        window_start = baseline_window_end
    else:
        window_start = now - timedelta(days=args.window_days)

    app = load_application(args.manifest)
    try:
        feedback_records = (
            app.feedback_sink.list_since(window_start) if app.feedback_sink is not None else []
        )
        document_records = (
            app.lifecycle_ledger.export_all() if app.lifecycle_ledger is not None else []
        )
        pending = app.review_queue.pending if app.review_queue is not None else None
        pending_count = len(pending) if pending is not None else 0
        count_resolved = getattr(app.review_queue, "count_resolved", None)
        resolved_count = count_resolved() if count_resolved is not None else 0
    finally:
        app.close()

    # `feedback_metrics.total` already excludes `is_test=True` records
    # (Codex review pass 1, MEDIUM-003) — reused as the escalation
    # denominator instead of `len(feedback_records)`, which would let
    # authorized test/QA traffic silently lower the reported escalation
    # rate and mask a real degradation.
    feedback_metrics = compute_feedback_drift_metrics(feedback_records)
    snapshot = DriftSnapshot(
        feedback=feedback_metrics,
        freshness=compute_document_freshness(
            document_records, stale_after_days=args.stale_after_days
        ),
        escalations=compute_escalation_metrics(
            pending_review_count=pending_count,
            resolved_review_count=resolved_count,
            total_feedback=feedback_metrics.total,
        ),
        generated_at=now,
    )
    payload = {
        "window_days": args.window_days,
        "window_start": window_start.isoformat(),
        "window_end": now.isoformat(),
        "feedback": asdict(snapshot.feedback),
        "freshness": asdict(snapshot.freshness),
        "escalations": asdict(snapshot.escalations),
        "generated_at": snapshot.generated_at.isoformat(),
    }
    print(json.dumps(payload, indent=2, default=str))

    if args.update_baseline:
        target = Path(args.baseline or "drift-baseline.json")
        target.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"Baseline updated: {target}")
        return 0

    if baseline_payload is None:
        print(
            "No --baseline given — nothing to compare against. "
            "Run with --update-baseline to create one."
        )
        return 0

    baseline_snapshot = DriftSnapshot(
        feedback=FeedbackDriftMetrics(**baseline_payload["feedback"]),
        freshness=DocumentFreshnessMetrics(**baseline_payload["freshness"]),
        escalations=EscalationMetrics(**baseline_payload["escalations"]),
        generated_at=datetime.fromisoformat(baseline_payload["generated_at"]),
    )
    report = compute_drift(snapshot, baseline_snapshot)
    if report.alerts:
        print("Drift alerts:")
        for alert in report.alerts:
            print(
                f"  - {alert.metric}: baseline={alert.baseline:.4f} "
                f"current={alert.current:.4f} delta={alert.delta:+.4f}"
            )
        if report.should_trigger_retraining:
            print("should_trigger_retraining=True")
    else:
        print("No drift alerts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
