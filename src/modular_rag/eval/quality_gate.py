"""Quality gates (Lot 13, docs/refactoring-plan.md — "begin gates in
report-only mode and promote agreed thresholds to blocking with recorded
baselines").

`QualityGate` compares an arbitrary `dict[str, float]` of metrics against a
recorded baseline. It's deliberately generic over the metric dict rather
than hardcoded to `BenchmarkReport` — callers build the dict themselves
(`BenchmarkReport.quality_summary()` is the intended source for "higher is
better" metrics; `BenchmarkReport.cost_summary()` for "lower is better"
ones — see `eval/runners/benchmark.py`).

Batch 13 (external plan — "Offline benchmark"): `lower_is_better` (below)
was added so one gate instance can also enforce cost/latency/failure-rate
regressions (worse == a larger number), not only quality regressions
(worse == a smaller number) — the "configurable quality gate" acceptance
criterion. Every metric not named in `lower_is_better` keeps the original
"higher is better" comparison, so this is purely additive: an existing
caller that never passes `lower_is_better` sees no behavior change.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum


class GateMode(StrEnum):
    REPORT_ONLY = "report_only"
    BLOCKING = "blocking"


@dataclass(frozen=True)
class GateViolation:
    metric: str
    baseline: float
    actual: float
    tolerance: float


class QualityGateError(Exception):
    """Raised by `QualityGate.check()` in `BLOCKING` mode when any metric
    regresses past its tolerance. Carries the full `GateResult` so a caller
    can inspect every violation, not just the first."""

    def __init__(self, result: GateResult) -> None:
        self.result = result
        violated = ", ".join(v.metric for v in result.violations)
        super().__init__(f"Quality gate failed (blocking mode): {violated}")


@dataclass
class GateResult:
    mode: GateMode
    passed: bool
    violations: list[GateViolation] = field(default_factory=list)


class QualityGate:
    """Compare actual metrics against a recorded baseline. In `REPORT_ONLY`
    mode (the default — "begin gates in report-only mode"), `check()` never
    raises regardless of violations; the caller is expected to inspect the
    returned `GateResult`. In `BLOCKING` mode, `check()` raises
    `QualityGateError` on any violation — the "promote agreed thresholds to
    blocking" half of the plan's phrasing.

    A metric present in `baseline` but missing from the `actual` dict passed
    to `check()` is treated as `0.0` for a "higher is better" metric
    (fail-closed: an unexpectedly absent metric looks like a regression, not
    a silent pass) — and, symmetrically, as `+inf` for a metric listed in
    `lower_is_better`, so a missing cost/latency reading also fails closed
    rather than looking like a suspiciously perfect zero.
    """

    def __init__(
        self,
        baseline: dict[str, float],
        *,
        mode: GateMode = GateMode.REPORT_ONLY,
        tolerance: float = 0.0,
        lower_is_better: frozenset[str] = frozenset(),
    ) -> None:
        self._baseline = dict(baseline)
        self._mode = mode
        self._tolerance = tolerance
        self._lower_is_better = lower_is_better

    def check(self, actual: dict[str, float]) -> GateResult:
        violations: list[GateViolation] = []
        for name, base in self._baseline.items():
            if name in self._lower_is_better:
                observed = actual.get(name, math.inf)
                regressed = observed > base + self._tolerance
            else:
                observed = actual.get(name, 0.0)
                regressed = observed < base - self._tolerance
            if regressed:
                violations.append(
                    GateViolation(
                        metric=name, baseline=base, actual=observed, tolerance=self._tolerance
                    )
                )
        result = GateResult(mode=self._mode, passed=not violations, violations=violations)
        if self._mode == GateMode.BLOCKING and violations:
            raise QualityGateError(result)
        return result
