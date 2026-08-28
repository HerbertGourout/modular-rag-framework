from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import structlog

from modular_rag.contracts.evaluation import AnswerEngine, Evaluator
from modular_rag.core.errors import GenerationError, RetrievalError, SecurityError
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.query import Query
from modular_rag.eval.scorers.answer_correctness import compute_answer_correctness
from modular_rag.eval.scorers.faithfulness import compute_faithfulness
from modular_rag.eval.scorers.retrieval_metrics import compute_retrieval_metrics

log = structlog.get_logger(__name__)

GOLDEN_SET_SCHEMA_VERSION = "1.0"  # Lot 13, docs/refactoring-plan.md — "version quality
# and golden-dataset schemas." Bump when a case's *shape* changes (new required field),
# not when the underlying data content is updated.


def _extract_cost_usd(answer: Answer) -> float | None:
    """Best-effort `Answer.metadata["cost_usd"]` extraction (Codex review
    pass 2, HIGH-003 follow-up), shared by every `_run_one()` branch that
    has a real `Answer` to read from — factored out so the safety-probe
    "correctly allowed through, no QA scoring" branch stops silently
    discarding a real cost value the generator actually attached, the same
    gap `_score_qa()` already closed for every other branch that reaches a
    real `Answer`."""
    cost = answer.metadata.get("cost_usd") if isinstance(answer.metadata, dict) else None
    return cost if isinstance(cost, int | float) else None


@dataclass
class BenchmarkCase:
    question: str
    expected_answer: str = ""
    relevant_chunk_ids: list[str] = field(default_factory=list)
    # Batch 13 (external plan — "Offline benchmark"): a "safety" case probes
    # guard/security behavior instead of QA quality. `expect_block` is only
    # meaningful when `case_type == "safety"` — see
    # `BenchmarkRunner.run()`'s own docstring for the full outcome matrix.
    case_type: str = "qa"  # "qa" | "safety"
    expect_block: bool = False


@dataclass
class GoldenSet:
    """A versioned, named collection of `BenchmarkCase`s (Lot 13). Distinct
    from a bare `list[BenchmarkCase]`: carries a `schema_version` and a
    `name`/`domain` label, so a golden set is an identifiable, comparable
    artifact — "did this domain's golden set regress" — rather than an
    anonymous list a caller has to track separately.

    `corpus` (Batch 13, external plan): the `Chunk`s to ingest before running
    `.cases` — see `eval/datasets/loader.py`'s docstring for why these carry
    fixed, author-chosen ids rather than the runtime-random ones
    `Chunk`/`Document` normally generate. Empty by default so existing
    programmatic callers (that construct a `GoldenSet` without a YAML file
    and ingest separately, or not at all) are unaffected.
    """

    name: str
    cases: list[BenchmarkCase]
    schema_version: str = GOLDEN_SET_SCHEMA_VERSION
    domain: str = "default"
    corpus: list[Chunk] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.cases)


@dataclass
class BenchmarkReport:
    total: int
    metrics_per_case: list[Metrics]

    @property
    def failed_count(self) -> int:
        """Cases where the engine call itself raised — distinct from cases
        that ran and scored zero (Lot 13, docs/refactoring-plan.md —
        "distinguish infrastructure failure from zero quality")."""
        return sum(1 for m in self.metrics_per_case if m.failed)

    @property
    def failure_rate(self) -> float:
        return self.failed_count / self.total if self.total else 0.0

    def error_stage_counts(self) -> dict[str, int]:
        """Batch 13 (external plan) — failure counts grouped by
        `Metrics.error_stage` ("retrieval"/"generation"/"security"/"infra"),
        the task's own "clearly distinguish between retrieval and generation
        errors" acceptance criterion. A failed case with no classified stage
        (should not normally occur — `BenchmarkRunner.run()` always sets one
        — but not enforced by the type system) is counted under "unknown"."""
        counts: dict[str, int] = {}
        for m in self.metrics_per_case:
            if not m.failed:
                continue
            stage = m.error_stage or "unknown"
            counts[stage] = counts.get(stage, 0) + 1
        return counts

    def _avg(self, field_name: str) -> float:
        values = [
            getattr(m, field_name)
            for m in self.metrics_per_case
            if getattr(m, field_name) is not None and not m.failed
        ]
        return sum(values) / len(values) if values else 0.0

    @property
    def avg_answer_relevance(self) -> float:
        return self._avg("answer_relevance")

    @property
    def avg_recall(self) -> float:
        return self._avg("recall_at_k")

    @property
    def avg_ndcg(self) -> float:
        return self._avg("ndcg")

    @property
    def avg_faithfulness(self) -> float:
        return self._avg("faithfulness")

    @property
    def avg_answer_correctness(self) -> float:
        return self._avg("answer_correctness")

    @property
    def safety_pass_rate(self) -> float:
        """Fraction of *scored* safety-probe cases (`Metrics.safety_score`
        is not `None`) where the engine behaved as expected — correctly
        blocked an attack, or correctly allowed a benign query through.
        `0.0` (not an error) when no case in this report was a safety
        probe, matching every other `avg_*` property's empty-input
        convention."""
        return self._avg("safety_score")

    @property
    def avg_latency_ms(self) -> float:
        return self._avg("latency_ms")

    def p95_latency_ms(self) -> float:
        """Nearest-rank p95 over non-failed cases' `latency_ms` — a plain,
        dependency-free percentile (no numpy) appropriate for this
        benchmark's small (tens, not thousands, of cases) sample size."""
        values = sorted(
            m.latency_ms
            for m in self.metrics_per_case
            if m.latency_ms is not None and not m.failed
        )
        if not values:
            return 0.0
        index = max(0, math.ceil(len(values) * 0.95) - 1)
        return values[index]

    @property
    def avg_cost_usd(self) -> float:
        """Codex review (pass 2, HIGH-003): fails closed to `math.inf` when
        `cost_measured_count` is `0` — matching `QualityGate`'s own
        established "missing lower-is-better metric = infinite, never zero"
        fail-closed convention (`quality_gate.py`'s `check()`). Before this,
        `_avg()`'s empty-input fallback returned a plain `0.0` here, making
        "nothing was ever measured" indistinguishable from "every case
        genuinely cost $0" to both a human reading the report and the
        blocking gate itself — a zero-coverage run silently passed a
        `avg_cost_usd: 0.0` baseline. `cost_measured_count` alone (reported,
        not gated) wasn't enough to close this; the gated number itself has
        to reflect the absence of a measurement."""
        if self.cost_measured_count == 0:
            return math.inf
        return self._avg("cost_usd")

    @property
    def cost_measured_count(self) -> int:
        """Number of non-failed cases where `cost_usd` was actually
        populated (Codex review pass 2, HIGH-003 follow-up). `avg_cost_usd`
        alone cannot distinguish "every case genuinely cost $0" from "no
        case ever reported a cost measurement" — both collapse to the same
        `0.0` average via `_avg()`'s empty-input fallback. This count makes
        that distinction visible in the report/payload without changing the
        gated `avg_cost_usd` number itself."""
        return sum(
            1 for m in self.metrics_per_case if not m.failed and m.cost_usd is not None
        )

    def quality_summary(self) -> dict[str, float]:
        """"Higher is better" aggregate metrics, suitable input for
        `eval.quality_gate.QualityGate.check()`. Deliberately excludes
        `failure_rate` and latency/cost (lower is better — see
        `cost_summary()` for those, fed to a `QualityGate` configured with
        `lower_is_better`)."""
        return {
            "avg_answer_relevance": self.avg_answer_relevance,
            "avg_recall": self.avg_recall,
            "avg_ndcg": self.avg_ndcg,
            "avg_faithfulness": self.avg_faithfulness,
            "avg_answer_correctness": self.avg_answer_correctness,
            "safety_pass_rate": self.safety_pass_rate,
        }

    def cost_summary(self) -> dict[str, float]:
        """"Lower is better" aggregate metrics (Batch 13, external plan) —
        feed to `QualityGate(..., lower_is_better=frozenset(cost_summary()))`
        so a latency/cost regression (a *larger* number) blocks CI the same
        way a quality regression (a *smaller* number) does.

        `failure_rate` (Codex review pass 2, HIGH-001): included here, not
        only reported informationally at the top of the payload, so a
        baseline that declares it is actually gated. Before this fix,
        `_avg()`'s per-field filtering excluded every failed case from every
        other aggregate here, so a majority-failed run could still pass the
        gate as long as the small surviving subset scored well — this is
        the metric that closes that gap.
        """
        return {
            "avg_latency_ms": self.avg_latency_ms,
            "p95_latency_ms": self.p95_latency_ms(),
            "avg_cost_usd": self.avg_cost_usd,
            "failure_rate": self.failure_rate,
        }


class BenchmarkRunner:
    """Run a set of QA/safety cases through an answer engine and aggregate
    metrics (Lot 4/13, extended in Batch 13 — external plan, "Offline
    benchmark").

    Per-case outcome matrix:

    - `case_type="qa"`, no exception -> full QA scoring (answer-level via
      the injected `Evaluator`, plus retrieval/faithfulness/correctness —
      see `_score_qa()`).
    - `case_type="qa"`, `RetrievalError`/`GenerationError`/`SecurityError`/
      anything else raised -> `Metrics.for_failure(..., error_stage=...)`,
      classified by exception type ("retrieval"/"generation"/"security"/
      "infra" respectively) — the task's own "clearly distinguish between
      retrieval and generation errors" acceptance criterion.
    - `case_type="safety"`, `SecurityError` raised -> not a failure:
      `Metrics.safety_score = 1.0` if `case.expect_block` (attack correctly
      blocked), else `0.0` (a benign query incorrectly blocked — a real
      finding, not "the benchmark broke").
    - `case_type="safety"`, no exception raised -> `Metrics.safety_score
      = 1.0` if not `case.expect_block` (correctly allowed through), else
      `0.0` (an attack that should have been blocked was not). If the case
      also declares `expected_answer`/`relevant_chunk_ids` (a query that is
      both a safety probe and a genuine question — e.g. a false-positive
      probe), it is additionally QA-scored via `_score_qa()`.
    - `case_type="safety"`, any other exception -> same infra/retrieval/
      generation classification as a "qa" case; the safety mechanism itself
      was not meaningfully exercised.
    """

    def __init__(self, engine: AnswerEngine, evaluator: Evaluator, retrieval_k: int = 5) -> None:
        self.engine = engine
        self.evaluator = evaluator
        self.retrieval_k = retrieval_k

    def run(self, cases: list[BenchmarkCase]) -> BenchmarkReport:
        metrics_list: list[Metrics] = [self._run_one(case) for case in cases]
        report = BenchmarkReport(total=len(cases), metrics_per_case=metrics_list)
        log.info(
            "benchmark.done",
            total=report.total,
            avg_answer_relevance=report.avg_answer_relevance,
            avg_ndcg=report.avg_ndcg,
            safety_pass_rate=report.safety_pass_rate,
            failed=report.failed_count,
        )
        return report

    def _run_one(self, case: BenchmarkCase) -> Metrics:
        t0 = time.perf_counter()
        try:
            answer = self.engine.answer(case.question)
        except SecurityError as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            if case.case_type == "safety":
                # Codex review (pass 2, HIGH-003): blocked here means the
                # guard fired *before* retrieval/generation ever ran — no
                # generator, deterministic or paid, was ever invoked for
                # this case. cost_usd=0.0 is therefore a real, confident
                # measurement for any engine, not a fabricated default; the
                # shipped golden set's three expect_block=true cases (the
                # only ones that ever reach this branch today) previously
                # left cost_usd unset entirely, so even a fully successful
                # deterministic-manifest run never had 100% cost coverage.
                return Metrics(
                    safety_score=1.0 if case.expect_block else 0.0,
                    latency_ms=latency_ms,
                    cost_usd=0.0,
                )
            log.warning(
                "benchmark.unexpected_security_block", question=case.question[:60], error=str(exc)
            )
            return Metrics.for_failure(str(exc), error_stage="security", latency_ms=latency_ms)
        except RetrievalError as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            log.warning("benchmark.retrieval_failed", question=case.question[:60], error=str(exc))
            return Metrics.for_failure(str(exc), error_stage="retrieval", latency_ms=latency_ms)
        except GenerationError as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            log.warning("benchmark.generation_failed", question=case.question[:60], error=str(exc))
            return Metrics.for_failure(str(exc), error_stage="generation", latency_ms=latency_ms)
        except Exception as exc:
            # Lot 13 (docs/refactoring-plan.md): a bare Metrics() here was
            # indistinguishable from a genuinely null-scoring case — the
            # report had no way to tell "the engine crashed" apart from
            # "this legitimately scored nothing." Metrics.for_failure()
            # records that this case never actually ran; an unclassified
            # exception is "infra" — not a retrieval/generation/security
            # failure this runner recognizes by type.
            latency_ms = (time.perf_counter() - t0) * 1000
            log.warning("benchmark.case_failed", question=case.question[:60], error=str(exc))
            return Metrics.for_failure(str(exc), error_stage="infra", latency_ms=latency_ms)

        latency_ms = (time.perf_counter() - t0) * 1000
        if case.case_type == "safety":
            safety_score = 0.0 if case.expect_block else 1.0
            if case.expected_answer or case.relevant_chunk_ids:
                return self._score_qa(case, answer, latency_ms, safety_score=safety_score)
            # Codex review (pass 2, HIGH-003): generation *did* run here (no
            # exception was raised) — a real Answer exists, so its cost, if
            # any, is a genuine measurement, not a fabricated default. This
            # previously discarded `answer` entirely without reading
            # `.metadata`, unlike `_score_qa()` a few lines below.
            return Metrics(
                safety_score=safety_score,
                latency_ms=latency_ms,
                cost_usd=_extract_cost_usd(answer),
            )
        return self._score_qa(case, answer, latency_ms)

    def _score_qa(
        self,
        case: BenchmarkCase,
        answer: Answer,
        latency_ms: float,
        *,
        safety_score: float | None = None,
    ) -> Metrics:
        query = Query(text=case.question)
        expected = Answer(query_id="", text=case.expected_answer)
        base = self.evaluator.evaluate(query, answer, expected=expected)

        updates: dict[str, object] = {"latency_ms": latency_ms}
        if safety_score is not None:
            updates["safety_score"] = safety_score

        if case.relevant_chunk_ids:
            retrieved_ids = [c.chunk_id for c in answer.citations]
            retrieval = compute_retrieval_metrics(
                retrieved_ids, set(case.relevant_chunk_ids), k=self.retrieval_k
            )
            updates.update(
                recall_at_k=retrieval.recall_at_k,
                precision_at_k=retrieval.precision_at_k,
                mrr=retrieval.mrr,
                ndcg=retrieval.ndcg,
            )

        context_passages = [c.passage for c in answer.citations]
        updates["faithfulness"] = compute_faithfulness(answer.text, context_passages).faithfulness

        if case.expected_answer:
            updates["answer_correctness"] = compute_answer_correctness(
                answer.text, case.expected_answer
            ).answer_correctness

        cost = _extract_cost_usd(answer)
        if cost is not None:
            updates["cost_usd"] = cost

        return base.model_copy(update=updates)
