"""Tests for eval/runners/benchmark.py.

Originally characterization tests (Lot 4, docs/refactoring-plan.md Part 2).
Lot 13 fixed the failure-masking bug the last test used to characterize —
that test now proves the fix instead. Batch 13 (external plan — "Offline
benchmark") added the safety-probe outcome matrix, error_stage
classification, and citation-based retrieval/faithfulness/correctness
scoring — see the new tests below and `BenchmarkRunner.run()`'s own
docstring for the full behavior this file locks in.
"""
from __future__ import annotations

import math

import pytest

from modular_rag.core.errors import GenerationError, RetrievalError, SecurityError
from modular_rag.core.models.answer import Answer, Citation
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.metrics import Metrics
from modular_rag.eval.runners.benchmark import (
    GOLDEN_SET_SCHEMA_VERSION,
    BenchmarkCase,
    BenchmarkReport,
    BenchmarkRunner,
    GoldenSet,
)


class _FakeEngine:
    def __init__(self, *, raise_on: str | None = None) -> None:
        self._raise_on = raise_on

    def answer(self, question: str, **kwargs: object) -> Answer:
        if self._raise_on is not None and question == self._raise_on:
            raise RuntimeError(f"engine exploded on: {question}")
        return Answer(query_id="q", text=question.upper())


class _RaisingEngine:
    """Raises a specific, caller-chosen exception type for every question —
    used to exercise `BenchmarkRunner`'s per-exception-type error_stage
    classification."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def answer(self, question: str, **kwargs: object) -> Answer:
        raise self._exc


class _CitingEngine:
    """Returns an `Answer` with real citations, so retrieval/faithfulness
    scoring (which reads `Answer.citations`, not a separate retrieve() call)
    has something to score."""

    def __init__(self, citations: list[Citation], text: str = "the retrieved passage text") -> None:
        self._citations = citations
        self._text = text

    def answer(self, question: str, **kwargs: object) -> Answer:
        return Answer(query_id="q", text=self._text, citations=self._citations)


class _FakeEvaluator:
    def name(self) -> str:
        return "fake"

    def evaluate(self, query, answer, expected=None, context=None) -> Metrics:  # type: ignore[no-untyped-def]
        return Metrics(answer_relevance=1.0, recall_at_k=0.8)


def test_report_avg_answer_relevance_ignores_none_values() -> None:
    report = BenchmarkReport(
        total=3,
        metrics_per_case=[
            Metrics(answer_relevance=1.0),
            Metrics(answer_relevance=0.5),
            Metrics(answer_relevance=None),
        ],
    )

    assert report.avg_answer_relevance == 0.75


def test_report_avg_answer_relevance_is_zero_when_every_case_is_none() -> None:
    report = BenchmarkReport(total=2, metrics_per_case=[Metrics(), Metrics()])

    assert report.avg_answer_relevance == 0.0
    assert report.avg_recall == 0.0


def test_runner_evaluates_every_case_and_reports_averages() -> None:
    runner = BenchmarkRunner(engine=_FakeEngine(), evaluator=_FakeEvaluator())
    cases = [
        BenchmarkCase(question="What is RAG?", expected_answer="Retrieval-Augmented Generation"),
        BenchmarkCase(question="What is BM25?", expected_answer="A ranking function"),
    ]

    report = runner.run(cases)

    assert report.total == 2
    assert report.avg_answer_relevance == 1.0
    assert report.avg_recall == 0.8
    assert report.failed_count == 0
    assert report.failure_rate == 0.0


def test_runner_records_engine_failures_as_failed_not_as_null_scores() -> None:
    """Fixed in Lot 13 (docs/refactoring-plan.md — "distinguish infrastructure
    failure from zero quality"): a case whose engine call raises is now
    recorded with Metrics.failed=True, not a bare Metrics() indistinguishable
    from a genuinely null-scoring case."""
    runner = BenchmarkRunner(
        engine=_FakeEngine(raise_on="this one blows up"), evaluator=_FakeEvaluator()
    )
    cases = [
        BenchmarkCase(question="a normal question", expected_answer="a normal answer"),
        BenchmarkCase(question="this one blows up", expected_answer="never scored"),
    ]

    report = runner.run(cases)  # does not raise

    assert report.total == 2
    failed_case_metrics = report.metrics_per_case[1]
    assert failed_case_metrics.failed is True
    assert "engine exploded" in failed_case_metrics.failure_reason
    assert failed_case_metrics != Metrics()  # no longer indistinguishable
    assert report.failed_count == 1
    assert report.failure_rate == 0.5
    # The average still only counts the successful case — now explicit via
    # BenchmarkReport's `not m.failed` filter, not incidental to `is not None`.
    assert report.avg_answer_relevance == 1.0


def test_quality_summary_excludes_failure_rate() -> None:
    report = BenchmarkReport(
        total=2,
        metrics_per_case=[Metrics(answer_relevance=1.0, recall_at_k=0.8), Metrics.for_failure("x")],
    )

    summary = report.quality_summary()

    assert summary["avg_answer_relevance"] == 1.0
    assert summary["avg_recall"] == 0.8
    assert "failure_rate" not in summary
    # Batch 13 (external plan): quality_summary() grew new "higher is
    # better" fields alongside the two Lot 13 originals above -- excluded
    # from this equality check on purpose (see
    # test_quality_summary_includes_the_new_batch_13_metrics for those).
    assert set(summary) == {
        "avg_answer_relevance",
        "avg_recall",
        "avg_ndcg",
        "avg_faithfulness",
        "avg_answer_correctness",
        "safety_pass_rate",
    }


def test_golden_set_has_a_schema_version_and_len():
    cases = [BenchmarkCase(question="q1", expected_answer="a1")]
    golden = GoldenSet(name="finance-basics", cases=cases, domain="finance")

    assert golden.schema_version == GOLDEN_SET_SCHEMA_VERSION
    assert len(golden) == 1
    assert golden.domain == "finance"


def test_golden_set_corpus_defaults_to_empty_and_can_be_set():
    empty = GoldenSet(name="x", cases=[])
    assert empty.corpus == []

    chunk = Chunk(id="c1", doc_id="d1", content="hello")
    populated = GoldenSet(name="x", cases=[], corpus=[chunk])
    assert populated.corpus == [chunk]


# ---------------------------------------------------------------------------
# Batch 13 (external plan — "Offline benchmark"): error_stage classification.
# ---------------------------------------------------------------------------


def test_retrieval_error_is_classified_with_error_stage_retrieval():
    runner = BenchmarkRunner(
        engine=_RaisingEngine(RetrievalError("qdrant unreachable")), evaluator=_FakeEvaluator()
    )

    report = runner.run([BenchmarkCase(question="q", expected_answer="a")])

    m = report.metrics_per_case[0]
    assert m.failed is True
    assert m.error_stage == "retrieval"
    assert report.error_stage_counts() == {"retrieval": 1}


def test_generation_error_is_classified_with_error_stage_generation():
    runner = BenchmarkRunner(
        engine=_RaisingEngine(GenerationError("llm call failed")), evaluator=_FakeEvaluator()
    )

    report = runner.run([BenchmarkCase(question="q", expected_answer="a")])

    assert report.metrics_per_case[0].error_stage == "generation"


def test_unexpected_security_block_on_a_qa_case_is_classified_as_error_stage_security():
    """A normal `qa` case that gets blocked was never meant to be blocked —
    a real failure, distinct from an expected safety-probe block."""
    runner = BenchmarkRunner(
        engine=_RaisingEngine(SecurityError("blocked")), evaluator=_FakeEvaluator()
    )

    report = runner.run([BenchmarkCase(question="q", expected_answer="a", case_type="qa")])

    m = report.metrics_per_case[0]
    assert m.failed is True
    assert m.error_stage == "security"
    assert m.safety_score is None  # not a safety probe -- not scored as one


def test_unclassified_exception_is_error_stage_infra():
    runner = BenchmarkRunner(
        engine=_RaisingEngine(RuntimeError("boom")), evaluator=_FakeEvaluator()
    )

    report = runner.run([BenchmarkCase(question="q", expected_answer="a")])

    assert report.metrics_per_case[0].error_stage == "infra"


# ---------------------------------------------------------------------------
# Batch 13: safety-probe outcome matrix.
# ---------------------------------------------------------------------------


def test_safety_case_correctly_blocked_scores_safety_one_and_is_not_a_failure():
    runner = BenchmarkRunner(
        engine=_RaisingEngine(SecurityError("blocked")), evaluator=_FakeEvaluator()
    )

    report = runner.run(
        [BenchmarkCase(question="attack", case_type="safety", expect_block=True)]
    )

    m = report.metrics_per_case[0]
    assert m.failed is False
    assert m.safety_score == 1.0
    assert report.safety_pass_rate == 1.0


def test_safety_case_attack_succeeded_scores_safety_zero_and_is_not_a_failure():
    """An attack that should have been blocked but wasn't is a real quality
    finding (a security regression), not an infra failure -- the case ran
    fine, it just failed the safety check."""
    runner = BenchmarkRunner(engine=_FakeEngine(), evaluator=_FakeEvaluator())

    report = runner.run(
        [BenchmarkCase(question="attack", case_type="safety", expect_block=True)]
    )

    m = report.metrics_per_case[0]
    assert m.failed is False
    assert m.safety_score == 0.0
    assert report.safety_pass_rate == 0.0


def test_safety_case_false_positive_block_scores_safety_zero():
    """A benign query (`expect_block=False`) that got blocked anyway is a
    false-positive over-blocking finding."""
    runner = BenchmarkRunner(
        engine=_RaisingEngine(SecurityError("blocked")), evaluator=_FakeEvaluator()
    )

    report = runner.run(
        [BenchmarkCase(question="benign", case_type="safety", expect_block=False)]
    )

    assert report.metrics_per_case[0].safety_score == 0.0


def test_safety_case_correctly_allowed_through_scores_safety_one():
    runner = BenchmarkRunner(engine=_FakeEngine(), evaluator=_FakeEvaluator())

    report = runner.run(
        [BenchmarkCase(question="benign", case_type="safety", expect_block=False)]
    )

    assert report.metrics_per_case[0].safety_score == 1.0


def test_safety_case_with_expected_answer_is_also_qa_scored():
    """A false-positive probe that is also a genuine question (this repo's
    own golden set has exactly one such case) gets both a safety_score and
    the normal QA metrics."""
    runner = BenchmarkRunner(engine=_FakeEngine(), evaluator=_FakeEvaluator())

    report = runner.run(
        [
            BenchmarkCase(
                question="what must I do",
                case_type="safety",
                expect_block=False,
                expected_answer="something",
            )
        ]
    )

    m = report.metrics_per_case[0]
    assert m.safety_score == 1.0
    assert m.answer_relevance == 1.0  # from _FakeEvaluator, proves QA scoring ran too


def test_safety_case_without_expected_answer_is_not_qa_scored():
    """A pure attack probe (no expected_answer/relevant_chunk_ids) is scored
    only on safety_score -- there is no gold answer to compare against."""
    runner = BenchmarkRunner(engine=_FakeEngine(), evaluator=_FakeEvaluator())

    report = runner.run([BenchmarkCase(question="attack", case_type="safety", expect_block=False)])

    m = report.metrics_per_case[0]
    assert m.safety_score == 1.0
    assert m.answer_relevance is None  # _FakeEvaluator was never called


def test_safety_pass_rate_is_zero_when_there_are_no_safety_cases():
    report = BenchmarkReport(total=1, metrics_per_case=[Metrics(answer_relevance=1.0)])

    assert report.safety_pass_rate == 0.0


# ---------------------------------------------------------------------------
# Codex review (pass 2, HIGH-003): a blocked-pre-generation safety case, and
# an allowed-through-with-no-QA-scoring safety case, both silently dropped
# cost_usd even when it was a real, knowable value.
# ---------------------------------------------------------------------------


class _MeteredEngine:
    """Returns an `Answer` carrying a real `cost_usd` in its metadata, the
    same shape a real generator (or DeterministicGenerator, post-HIGH-003)
    produces -- used to prove a benchmark branch actually reads it."""

    def __init__(self, cost_usd: float) -> None:
        self._cost_usd = cost_usd

    def answer(self, question: str, **kwargs: object) -> Answer:
        return Answer(query_id="q", text=question.upper(), metadata={"cost_usd": self._cost_usd})


def test_expected_block_safety_case_records_a_real_zero_cost():
    """Blocked before retrieval/generation ever run -- no generator, real or
    deterministic, was invoked, so cost_usd=0.0 is a genuine measurement,
    not a fabricated default. The shipped golden set's three
    expect_block=true cases are exactly this branch."""
    runner = BenchmarkRunner(
        engine=_RaisingEngine(SecurityError("blocked")), evaluator=_FakeEvaluator()
    )

    report = runner.run(
        [BenchmarkCase(question="attack", case_type="safety", expect_block=True)]
    )

    assert report.metrics_per_case[0].cost_usd == 0.0


def test_safety_case_allowed_through_with_no_qa_scoring_still_captures_real_cost():
    """Generation *did* run here (no exception raised) -- a real cost value
    on the returned Answer must not be silently discarded just because this
    case has no expected_answer/relevant_chunk_ids to QA-score against."""
    runner = BenchmarkRunner(engine=_MeteredEngine(cost_usd=0.0042), evaluator=_FakeEvaluator())

    report = runner.run(
        [BenchmarkCase(question="attack", case_type="safety", expect_block=False)]
    )

    m = report.metrics_per_case[0]
    assert m.safety_score == 1.0  # unaffected -- this case is not itself a regression
    assert m.cost_usd == 0.0042


def test_a_full_safety_and_qa_run_reaches_full_cost_coverage():
    """Reproduces the real shipped core_v1.yaml's exact case-type shape (9 qa
    + 3 expect_block=true safety + 1 expect_block=false safety-with-QA) with
    fakes, and confirms every single case now ends up with a measured cost
    -- the concrete gap the review's own evidence demonstrated (10/13, not
    13/13, before this fix)."""
    engine = _MeteredEngine(cost_usd=0.0)
    runner = BenchmarkRunner(engine=engine, evaluator=_FakeEvaluator())
    cases = (
        [BenchmarkCase(question=f"qa {i}", expected_answer="a") for i in range(9)]
        + [
            BenchmarkCase(question=f"attack {i}", case_type="safety", expect_block=True)
            for i in range(3)
        ]
        + [
            BenchmarkCase(
                question="what must I do",
                case_type="safety",
                expect_block=False,
                expected_answer="something",
            )
        ]
    )
    # The three expect_block=true cases need the engine to actually block --
    # a separate runner/engine pair reproduces that specific branch, already
    # covered by test_expected_block_safety_case_records_a_real_zero_cost;
    # here we only need the remaining 10 cases (which this engine allows
    # through) to reach full coverage on their own.
    qa_and_allowed_cases = [c for c in cases if not (c.case_type == "safety" and c.expect_block)]
    report = runner.run(qa_and_allowed_cases)

    assert report.total == 10
    assert report.cost_measured_count == 10


def test_avg_cost_usd_fails_closed_to_infinity_when_nothing_was_measured():
    """Codex review (pass 2, HIGH-003): before this fix, zero measured cases
    still returned avg_cost_usd=0.0 via _avg()'s empty-input fallback,
    indistinguishable from a real, confirmed zero -- a zero-coverage report
    silently passed a `avg_cost_usd: 0.0` gate. Reproduces the review's own
    exact repro shape (two successful Metrics() objects, no cost_usd)."""
    report = BenchmarkReport(total=2, metrics_per_case=[Metrics(), Metrics()])

    assert report.cost_measured_count == 0
    assert report.avg_cost_usd == math.inf
    assert report.cost_summary()["avg_cost_usd"] == math.inf


def test_zero_cost_coverage_report_fails_a_blocking_gate():
    """Direct reproduction of the review's own evidence: a zero-coverage
    report used to report avg_cost_usd=0.0 and PASS the blocking gate at a
    0.0 baseline. It must now fail, since a missing measurement is no longer
    indistinguishable from a confirmed zero."""
    from modular_rag.eval.quality_gate import GateMode, QualityGate, QualityGateError

    report = BenchmarkReport(
        total=2, metrics_per_case=[Metrics(answer_relevance=1.0), Metrics(answer_relevance=1.0)]
    )
    assert report.cost_measured_count == 0

    gate = QualityGate(
        {"avg_cost_usd": 0.0},
        mode=GateMode.BLOCKING,
        lower_is_better=frozenset({"avg_cost_usd"}),
    )

    with pytest.raises(QualityGateError) as exc_info:
        gate.check(report.cost_summary())

    assert exc_info.value.result.violations[0].metric == "avg_cost_usd"
    assert exc_info.value.result.violations[0].actual == math.inf


# ---------------------------------------------------------------------------
# Batch 13: citation-based retrieval/faithfulness/correctness scoring.
# ---------------------------------------------------------------------------


def _citation(chunk_id: str, passage: str) -> Citation:
    return Citation(chunk_id=chunk_id, source="doc", passage=passage, score=1.0)


def test_qa_case_scores_retrieval_metrics_from_answer_citations():
    engine = _CitingEngine(
        citations=[_citation("c1", "the right passage"), _citation("c2", "a distractor")]
    )
    runner = BenchmarkRunner(engine=engine, evaluator=_FakeEvaluator())

    report = runner.run(
        [BenchmarkCase(question="q", expected_answer="a", relevant_chunk_ids=["c1"])]
    )

    m = report.metrics_per_case[0]
    assert m.recall_at_k == 1.0  # "c1" is present
    assert m.mrr == 1.0  # "c1" ranked first
    assert m.ndcg == 1.0  # ideal ordering for k>=1 relevant id


def test_qa_case_without_relevant_chunk_ids_skips_retrieval_scoring():
    """No declared relevant ids -> nothing meaningful to score against ->
    retrieval fields stay whatever the injected Evaluator returned, not
    overwritten with a misleading 0.0."""
    engine = _CitingEngine(citations=[_citation("c1", "some passage")])
    runner = BenchmarkRunner(engine=engine, evaluator=_FakeEvaluator())

    report = runner.run([BenchmarkCase(question="q", expected_answer="a")])

    assert report.metrics_per_case[0].recall_at_k == 0.8  # untouched, from _FakeEvaluator


def test_qa_case_scores_faithfulness_from_citation_passages():
    engine = _CitingEngine(
        citations=[_citation("c1", "the refund window is 30 days")],
        text="the refund window is 30 days",
    )
    runner = BenchmarkRunner(engine=engine, evaluator=_FakeEvaluator())

    report = runner.run([BenchmarkCase(question="q", expected_answer="30 days")])

    assert report.metrics_per_case[0].faithfulness == 1.0


def test_qa_case_scores_answer_correctness_against_expected_answer():
    engine = _CitingEngine(citations=[], text="30 days")
    runner = BenchmarkRunner(engine=engine, evaluator=_FakeEvaluator())

    report = runner.run([BenchmarkCase(question="q", expected_answer="30 days")])

    assert report.metrics_per_case[0].answer_correctness == 1.0


def test_case_without_expected_answer_skips_answer_correctness():
    engine = _CitingEngine(citations=[], text="anything")
    runner = BenchmarkRunner(engine=engine, evaluator=_FakeEvaluator())

    report = runner.run([BenchmarkCase(question="q", expected_answer="")])

    assert report.metrics_per_case[0].answer_correctness is None


def test_latency_is_recorded_for_a_successful_case():
    runner = BenchmarkRunner(engine=_FakeEngine(), evaluator=_FakeEvaluator())

    report = runner.run([BenchmarkCase(question="q", expected_answer="a")])

    assert report.metrics_per_case[0].latency_ms is not None
    assert report.metrics_per_case[0].latency_ms >= 0.0
    assert report.avg_latency_ms >= 0.0


def test_report_p95_latency_ms_is_zero_when_no_case_has_latency():
    report = BenchmarkReport(total=1, metrics_per_case=[Metrics()])

    assert report.p95_latency_ms() == 0.0


def test_report_p95_latency_ms_picks_the_nearest_rank_value():
    report = BenchmarkReport(
        total=4,
        metrics_per_case=[Metrics(latency_ms=v) for v in [10.0, 20.0, 30.0, 100.0]],
    )

    # ceil(4 * 0.95) - 1 = ceil(3.8) - 1 = 4 - 1 = 3 -> the highest value
    assert report.p95_latency_ms() == 100.0


def test_quality_summary_includes_the_new_batch_13_metrics():
    report = BenchmarkReport(
        total=1,
        metrics_per_case=[
            Metrics(
                answer_relevance=1.0,
                recall_at_k=1.0,
                ndcg=1.0,
                faithfulness=1.0,
                answer_correctness=1.0,
                safety_score=1.0,
            )
        ],
    )

    summary = report.quality_summary()

    assert summary == {
        "avg_answer_relevance": 1.0,
        "avg_recall": 1.0,
        "avg_ndcg": 1.0,
        "avg_faithfulness": 1.0,
        "avg_answer_correctness": 1.0,
        "safety_pass_rate": 1.0,
    }


def test_cost_summary_is_separate_from_quality_summary():
    report = BenchmarkReport(
        total=1, metrics_per_case=[Metrics(latency_ms=100.0, cost_usd=0.01)]
    )

    cost = report.cost_summary()

    assert cost == {
        "avg_latency_ms": 100.0,
        "p95_latency_ms": 100.0,
        "avg_cost_usd": 0.01,
        "failure_rate": 0.0,
    }
    assert "avg_latency_ms" not in report.quality_summary()


# ---------------------------------------------------------------------------
# Codex review (pass 1, HIGH-001): the blocking gate must not pass with a
# majority of cases failed. `failure_rate` is now included in
# `cost_summary()` (the gated "lower is better" dict) specifically to close
# this.
# ---------------------------------------------------------------------------


def test_cost_measured_count_distinguishes_unmeasured_from_a_real_zero():
    """Codex review (pass 1 HIGH-003, tightened at pass 2): `cost_measured_count`
    makes "no case ever reported a cost" visible; `avg_cost_usd` itself now
    fails closed to `math.inf` in that case (see
    test_avg_cost_usd_fails_closed_to_infinity_when_nothing_was_measured)
    rather than the ambiguous 0.0 an earlier version of this fix left in
    place."""
    unmeasured = BenchmarkReport(total=2, metrics_per_case=[Metrics(), Metrics()])
    assert unmeasured.avg_cost_usd == math.inf
    assert unmeasured.cost_measured_count == 0

    measured = BenchmarkReport(
        total=2, metrics_per_case=[Metrics(cost_usd=0.0), Metrics(cost_usd=0.0)]
    )
    assert measured.avg_cost_usd == 0.0
    assert measured.cost_measured_count == 2

    # A failed case's cost_usd is never counted, even if somehow set.
    failed_with_cost = Metrics.for_failure("x")
    with_a_failure = BenchmarkReport(
        total=2, metrics_per_case=[Metrics(cost_usd=0.0), failed_with_cost]
    )
    assert with_a_failure.cost_measured_count == 1


def test_cost_summary_includes_failure_rate_for_gating():
    report = BenchmarkReport(
        total=4,
        metrics_per_case=[
            Metrics(latency_ms=10.0),
            Metrics.for_failure("x", latency_ms=5.0),
            Metrics.for_failure("y", latency_ms=5.0),
            Metrics.for_failure("z", latency_ms=5.0),
        ],
    )

    assert report.cost_summary()["failure_rate"] == 0.75


def test_failed_cases_now_record_latency_across_every_error_stage():
    """Codex review (pass 1, HIGH-001 follow-up): `Metrics.for_failure()`
    used to leave `latency_ms=None` for every failure branch — the guide
    claims "every case records latency_ms," which was false for a failed
    one. Covers all four classified stages, matching `_run_one()`'s branches."""
    for exc, stage in [
        (RetrievalError("x"), "retrieval"),
        (GenerationError("x"), "generation"),
        (RuntimeError("x"), "infra"),
    ]:
        runner = BenchmarkRunner(engine=_RaisingEngine(exc), evaluator=_FakeEvaluator())
        report = runner.run([BenchmarkCase(question="q", expected_answer="a")])
        m = report.metrics_per_case[0]
        assert m.error_stage == stage
        assert m.latency_ms is not None
        assert m.latency_ms >= 0.0

    # The unexpected-security-block branch is its own code path (case_type
    # stays "qa" but a SecurityError is raised) -- covered separately since
    # it previously computed latency_ms and then discarded it.
    runner = BenchmarkRunner(
        engine=_RaisingEngine(SecurityError("blocked")), evaluator=_FakeEvaluator()
    )
    report = runner.run([BenchmarkCase(question="q", expected_answer="a", case_type="qa")])
    m = report.metrics_per_case[0]
    assert m.error_stage == "security"
    assert m.latency_ms is not None
    assert m.latency_ms >= 0.0


def test_a_majority_failed_report_fails_a_quality_gate_configured_with_failure_rate():
    """Direct reproduction of the Codex review's own evidence: 1 perfect QA
    result, 4 passing safety results, 8 infra failures (61.54% failure rate)
    must now be rejected by a gate whose baseline declares failure_rate,
    where before this fix it passed regardless."""
    from modular_rag.eval.quality_gate import GateMode, QualityGate, QualityGateError

    metrics_per_case = (
        [Metrics(answer_relevance=1.0, recall_at_k=1.0, ndcg=1.0, faithfulness=1.0)]
        + [Metrics(safety_score=1.0) for _ in range(4)]
        + [Metrics.for_failure("engine exploded", error_stage="infra") for _ in range(8)]
    )
    report = BenchmarkReport(total=13, metrics_per_case=metrics_per_case)
    assert round(report.failure_rate, 4) == round(8 / 13, 4)

    gate = QualityGate(
        {
            **report.quality_summary(),
            "avg_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "avg_cost_usd": 0.0,
            "failure_rate": 0.0,
        },
        mode=GateMode.BLOCKING,
        lower_is_better=frozenset(
            {"avg_latency_ms", "p95_latency_ms", "avg_cost_usd", "failure_rate"}
        ),
    )

    # Before the fix: gating on report.quality_summary()/cost_summary() alone
    # never saw failure_rate at all, so this same report passed silently.
    with pytest.raises(QualityGateError) as exc_info:
        gate.check({**report.quality_summary(), **report.cost_summary()})

    assert any(v.metric == "failure_rate" for v in exc_info.value.result.violations)
