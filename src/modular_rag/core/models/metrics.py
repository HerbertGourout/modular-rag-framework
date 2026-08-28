from __future__ import annotations

from pydantic import BaseModel

METRICS_SCHEMA_VERSION = "1.0"  # Lot 13, docs/refactoring-plan.md — "version quality and
# golden-dataset schemas." Bump when a field's *meaning* changes (e.g. a metric's formula),
# not when a purely additive field is introduced.

# Field names never included in .summary()'s output — metadata about the Metrics instance
# itself, not a scored quality dimension. `failed`/`failure_reason` default to non-None
# values (False/None respectively via schema_version's str default), so without this
# exclusion they'd always appear in every summary regardless of what was actually scored.
_SUMMARY_EXCLUDED_FIELDS = frozenset({"schema_version", "failed", "failure_reason"})


class Metrics(BaseModel):
    schema_version: str = METRICS_SCHEMA_VERSION

    # -- Retrieval: over retrieved chunks vs. a relevant-chunk-id set --
    recall_at_k: float | None = None
    precision_at_k: float | None = None
    ndcg: float | None = None
    mrr: float | None = None

    # -- Answer: over generated answer text vs. an expected/gold answer --
    # Deliberately separate from the retrieval fields above (Lot 13,
    # docs/refactoring-plan.md — "correct metric vocabulary": `ExactMatchEvaluator`
    # previously wrote its answer-level precision/recall into `precision_at_k`/
    # `recall_at_k`, which are retrieval-scoped fields per `eval/scorers/retrieval_metrics.py`).
    exact_match: float | None = None  # 1.0/0.0 — genuine normalized string equality
    answer_precision: float | None = None  # token-set precision, answer vs. gold
    answer_recall: float | None = None  # token-set recall, answer vs. gold
    answer_relevance: float | None = None  # token-set F1, answer vs. gold
    answer_correctness: float | None = None  # Batch 13 (external plan) — sequence-similarity
    # proxy, answer vs. gold; distinct from answer_relevance's bag-of-words F1 (order/phrase
    # sensitive where answer_relevance is not). See eval/scorers/answer_correctness.py.
    groundedness: float | None = None
    faithfulness: float | None = None  # Batch 13 — token-overlap proxy, answer vs. retrieved
    # context (not an LLM-judge score). See eval/scorers/faithfulness.py.
    context_precision: float | None = None

    # -- Policy/governance --
    policy_violations: int | None = None

    # -- Safety (Batch 13, external plan — "Offline benchmark") --
    safety_score: float | None = None  # 1.0/0.0 — did the engine behave as expected on a
    # safety-probe case (correctly blocked an attack, or correctly allowed a benign query)?
    # None for a regular "qa" case this was never scored for.

    # -- Cost/latency --
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None

    # -- Failure signal (Lot 13: "distinguish infrastructure failure from zero
    # quality") -- a case whose engine call raised must be recorded as `failed`,
    # never as a bare all-None Metrics indistinguishable from a genuine null score.
    failed: bool = False
    failure_reason: str | None = None
    error_stage: str | None = None  # Batch 13 (external plan) — one of "retrieval",
    # "generation", "security", "infra" when `failed` is True; None otherwise. Lets a report
    # separate "the retriever crashed" from "the generator crashed" instead of one opaque
    # failure bucket (the task's own "clearly distinguish between retrieval and generation
    # errors" acceptance criterion). See eval/runners/benchmark.py::BenchmarkRunner.run().

    def summary(self) -> dict[str, float]:
        return {
            k: v
            for k, v in self.model_dump().items()
            if v is not None and k not in _SUMMARY_EXCLUDED_FIELDS
        }

    @classmethod
    def for_failure(
        cls, reason: str, error_stage: str | None = None, latency_ms: float | None = None
    ) -> Metrics:
        """Build a `Metrics` for a case that failed to run at all (e.g. the
        engine raised) — every quality field stays `None` (there is nothing
        to score), but `failed`/`failure_reason` make that explicit instead
        of leaving a null-scored case and a crashed case looking identical.

        `error_stage` (Batch 13, external plan): one of "retrieval",
        "generation", "security", "infra", or `None` when the caller could
        not classify the failure — see `Metrics.error_stage`'s own docstring.

        `latency_ms` (Codex review pass 2, HIGH-001 follow-up): a failed case
        still spent real wall-clock time before the engine raised — leaving
        this `None` here made a failed case's latency invisible even though
        `BenchmarkRunner._run_one()` measures it. Optional because a caller
        that genuinely has no elapsed-time measurement (e.g. a hand-built
        test fixture) should not be forced to fabricate one.
        """
        return cls(
            failed=True, failure_reason=reason, error_stage=error_stage, latency_ms=latency_ms
        )
