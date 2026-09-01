"""Unit tests for scripts/run_drift_check.py (Batch 14, ADR-0014). Unlike
scripts/run_benchmark.py's sibling test file, this script has no factored-out
pure helper functions to import directly — everything (argument parsing, the
`load_application()` call, the JSON round-trip) lives inline in `main()`. So
these tests monkeypatch `modular_rag.app.bootstrap.load_application` (the
name `main()`'s own lazy `from ... import load_application` resolves at call
time) with a fake `ApplicationService`-shaped object, and run the real
`main()` end to end against a `tmp_path` baseline file.

`_FakeFeedbackSink.list_since()` filters on `created_at`, matching
`InMemoryFeedbackSink`/`PostgresFeedbackSink`'s real `since`-boundary
semantics, and `.records` is a plain, public, append-only list — Codex
review pass 2's own HIGH-001 reproduction methodology requires ONE shared
store across a baseline-creation call and a later comparison call, never
swapped out for a second fake instance, since swapping stores is exactly
what let the pass-1 version of this test pass without the underlying bug
actually being fixed.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest

from modular_rag.contracts.feedback import Feedback, FeedbackRating


class _FakeFeedbackSink:
    def __init__(self, records: list[Feedback]) -> None:
        self.records: list[Feedback] = list(records)

    def list_since(self, since: datetime | None = None) -> list[Feedback]:
        if since is None:
            return list(self.records)
        return [r for r in self.records if r.created_at >= since]


class _FakeReviewQueue:
    pending: list[object] = []

    def count_resolved(self) -> int:
        return 0


class _FakeApp:
    def __init__(self, records: list[Feedback]) -> None:
        self.feedback_sink = _FakeFeedbackSink(records)
        self.lifecycle_ledger = None
        self.review_queue = _FakeReviewQueue()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _feedback(rating: FeedbackRating, key: str, *, created_at: datetime | None = None) -> Feedback:
    kwargs = {"trace_id": "t1", "idempotency_key": key, "rating": rating}
    if created_at is not None:
        kwargs["created_at"] = created_at
    return Feedback(**kwargs)


def _fixed_clock(fixed_now: datetime) -> type[datetime]:
    """A `datetime` subclass whose `.now()` always returns `fixed_now` —
    used to simulate "the baseline was taken N days ago" without an actual
    `time.sleep()`. `fromisoformat`/arithmetic are inherited unchanged from
    the real `datetime`, so this is safe to swap in for the whole class."""

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN201 -- matches datetime.now's own signature
            return fixed_now

    return _Fixed


def test_help_does_not_require_a_live_manifest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--help` exits before `load_application()` is ever called — mirrors
    `test_run_benchmark.py`'s identical convention for a script that
    otherwise needs a real manifest/backing service."""
    from scripts.run_drift_check import main

    monkeypatch.setattr(sys, "argv", ["run_drift_check.py", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--update-baseline" in out
    assert "--window-days" in out


@pytest.mark.parametrize("bad_value", ["0", "-1", "-7"])
def test_non_positive_window_days_is_rejected(
    bad_value: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Codex review pass 2, MEDIUM-004: a zero or negative --window-days
    previously computed a window boundary at or after "now", silently
    excluding all current feedback instead of failing loudly. Rejected
    before `load_application()` is ever called — no manifest needed."""
    from scripts.run_drift_check import main

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_drift_check.py", "--manifest", "unused.yaml", "--window-days", bad_value],
    )

    assert main() == 1
    assert "must be >= 1" in capsys.readouterr().out


def test_update_baseline_then_compare_round_trips_through_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end through the real `main()`: write a baseline from a mostly-
    happy feedback window, then — after enough simulated time has elapsed —
    compare a clearly-degraded window against that same baseline file,
    proving the write (asdict -> json.dumps) and read (json.loads ->
    FeedbackDriftMetrics(**payload)) sides actually agree with each other."""
    import scripts.run_drift_check as run_drift_check_module
    from scripts.run_drift_check import main

    import modular_rag.app.bootstrap as bootstrap_module

    real_now = datetime.now(UTC)
    baseline_time = real_now - timedelta(days=10)
    baseline_path = tmp_path / "drift-baseline.json"

    healthy_app = _FakeApp(
        [
            _feedback(FeedbackRating.THUMBS_UP, "k1", created_at=baseline_time - timedelta(days=1)),
            _feedback(FeedbackRating.THUMBS_UP, "k2", created_at=baseline_time - timedelta(days=1)),
        ]
    )
    monkeypatch.setattr(bootstrap_module, "load_application", lambda manifest: healthy_app)
    monkeypatch.setattr(run_drift_check_module, "datetime", _fixed_clock(baseline_time))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_drift_check.py",
            "--manifest",
            "unused.yaml",
            "--update-baseline",
            "--baseline",
            str(baseline_path),
            "--window-days",
            "7",
        ],
    )

    assert main() == 0
    assert baseline_path.exists()
    assert healthy_app.closed is True

    monkeypatch.setattr(run_drift_check_module, "datetime", datetime)  # real clock again
    degraded_app = _FakeApp(
        [
            _feedback(FeedbackRating.THUMBS_DOWN, "k3", created_at=real_now),
            _feedback(FeedbackRating.THUMBS_DOWN, "k4", created_at=real_now),
            _feedback(FeedbackRating.THUMBS_DOWN, "k5", created_at=real_now),
        ]
    )
    monkeypatch.setattr(bootstrap_module, "load_application", lambda manifest: degraded_app)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_drift_check.py",
            "--manifest",
            "unused.yaml",
            "--baseline",
            str(baseline_path),
            "--window-days",
            "7",
        ],
    )

    assert main() == 0
    out = capsys.readouterr().out
    assert "Drift alerts:" in out
    assert "thumbs_down_rate" in out
    assert "should_trigger_retraining=True" in out


def test_a_severe_recent_regression_is_not_diluted_by_overlapping_baseline_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Codex review pass 2's own reopened-HIGH-001 reproduction methodology:
    ONE single, append-only fake store shared across both the
    baseline-creation call and the comparison call — never swapped out for
    a second fake instance, which is exactly what let the pass-1 version of
    this test pass without the underlying overlapping-window bug actually
    being fixed (the review's own words: "do not replace the store or move
    baseline observations outside the configured window merely to make the
    test pass").

    10,000 healthy records already sit in the store when the baseline is
    taken (a fixed clock ten days in the past). Ten days later (the real
    clock), 100 severely negative records are appended to that *same*
    store — never a new one — and a comparison is run. Disjoint windows
    (baseline `[T0-7d, T0]`, current `[T0, now]`) mean the 10,000 old
    records fall entirely outside the current window even though they are
    still physically present in the store, so the regression is not
    diluted."""
    import scripts.run_drift_check as run_drift_check_module
    from scripts.run_drift_check import main

    import modular_rag.app.bootstrap as bootstrap_module

    real_now = datetime.now(UTC)
    baseline_time = real_now - timedelta(days=10)
    baseline_path = tmp_path / "drift-baseline.json"

    shared_app = _FakeApp(
        [
            _feedback(
                FeedbackRating.THUMBS_UP, f"h{i}", created_at=baseline_time - timedelta(days=1)
            )
            for i in range(10_000)
        ]
    )
    monkeypatch.setattr(bootstrap_module, "load_application", lambda manifest: shared_app)

    monkeypatch.setattr(run_drift_check_module, "datetime", _fixed_clock(baseline_time))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_drift_check.py",
            "--manifest",
            "unused.yaml",
            "--update-baseline",
            "--baseline",
            str(baseline_path),
            "--window-days",
            "7",
        ],
    )
    assert main() == 0
    capsys.readouterr()  # discard baseline-creation output

    # Ten (real) days later: append the regression directly into the SAME
    # store — it is never replaced.
    shared_app.feedback_sink.records.extend(
        _feedback(FeedbackRating.THUMBS_DOWN, f"new{i}", created_at=real_now) for i in range(100)
    )
    monkeypatch.setattr(run_drift_check_module, "datetime", datetime)  # real clock again
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_drift_check.py",
            "--manifest",
            "unused.yaml",
            "--baseline",
            str(baseline_path),
            "--window-days",
            "7",
        ],
    )

    assert main() == 0
    out = capsys.readouterr().out
    assert "Drift alerts:" in out
    assert "thumbs_down_rate" in out
    assert "should_trigger_retraining=True" in out


def test_comparing_too_soon_after_the_baseline_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Not enough time has elapsed since the baseline's own window ended
    for a `--window-days`-sized current window to be meaningful — rejected
    rather than silently compared against a too-short (and therefore
    noisy) current sample."""
    from scripts.run_drift_check import main

    import modular_rag.app.bootstrap as bootstrap_module

    baseline_path = tmp_path / "drift-baseline.json"
    app = _FakeApp([_feedback(FeedbackRating.THUMBS_UP, "k1")])
    monkeypatch.setattr(bootstrap_module, "load_application", lambda manifest: app)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_drift_check.py",
            "--manifest",
            "unused.yaml",
            "--update-baseline",
            "--baseline",
            str(baseline_path),
            "--window-days",
            "7",
        ],
    )
    assert main() == 0
    capsys.readouterr()

    # Compare immediately (no simulated elapsed time at all) with the same
    # 7-day minimum still in force.
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_drift_check.py",
            "--manifest",
            "unused.yaml",
            "--baseline",
            str(baseline_path),
            "--window-days",
            "7",
        ],
    )

    assert main() == 1
    assert "has elapsed since the baseline" in capsys.readouterr().out


def test_baseline_predating_disjoint_window_support_is_rejected_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A baseline written before this fix has no `window_end` key — reject
    with an actionable message instead of a raw KeyError/TypeError."""
    import json

    from scripts.run_drift_check import main

    import modular_rag.app.bootstrap as bootstrap_module

    baseline_path = tmp_path / "drift-baseline.json"
    baseline_path.write_text(json.dumps({"window_days": 7}), encoding="utf-8")
    app = _FakeApp([_feedback(FeedbackRating.THUMBS_UP, "k1")])
    monkeypatch.setattr(bootstrap_module, "load_application", lambda manifest: app)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_drift_check.py", "--manifest", "unused.yaml", "--baseline", str(baseline_path)],
    )

    assert main() == 1
    assert "predates disjoint-window support" in capsys.readouterr().out


def test_escalation_denominator_excludes_test_feedback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Codex review pass 1, MEDIUM-003: the escalation-rate denominator must
    use the already-filtered real-feedback total, not the raw record count
    (which would let `is_test=True` traffic silently lower the reported
    escalation rate)."""
    from scripts.run_drift_check import main

    import modular_rag.app.bootstrap as bootstrap_module

    class _PendingReviewQueue(_FakeReviewQueue):
        pending = [object()] * 10

    real_feedback = [_feedback(FeedbackRating.THUMBS_UP, f"r{i}") for i in range(10)]
    test_feedback = [
        Feedback(
            trace_id="t",
            idempotency_key=f"test{i}",
            rating=FeedbackRating.THUMBS_UP,
            is_test=True,
        )
        for i in range(90)
    ]
    app = _FakeApp(real_feedback + test_feedback)
    app.review_queue = _PendingReviewQueue()
    monkeypatch.setattr(bootstrap_module, "load_application", lambda manifest: app)
    monkeypatch.setattr(
        sys, "argv", ["run_drift_check.py", "--manifest", "unused.yaml"]
    )

    assert main() == 0
    out = capsys.readouterr().out
    # 10 pending / 10 real feedback == 1.0, not 10 / 100 == 0.1.
    assert '"pending_review_count": 10' in out
    assert '"escalation_rate": 1.0' in out
