"""Quality gates (Lot 13, docs/refactoring-plan.md — "begin gates in
report-only mode and promote agreed thresholds to blocking with recorded
baselines").

`QualityGate` compares an arbitrary `dict[str, float]` of "higher is
better" metrics against a recorded baseline. It's deliberately generic over
the metric dict rather than hardcoded to `BenchmarkReport` — callers build
the dict themselves (`BenchmarkReport.quality_summary()` is the intended
source), which keeps this module from needing to know about report-shaped
data or about metrics whose "better" direction is inverted (e.g.
`failure_rate`, lower is better — not something this gate's comparison
logic supports, by design; gating on that needs a different comparison,
not shoehorned into the same one).
"""
from __future__ import annotations

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
    to `check()` is treated as `0.0` — fail-closed: an unexpectedly absent
    metric looks like a regression, not like a silent pass.
    """

    def __init__(
        self,
        baseline: dict[str, float],
        *,
        mode: GateMode = GateMode.REPORT_ONLY,
        tolerance: float = 0.0,
    ) -> None:
        self._baseline = dict(baseline)
        self._mode = mode
        self._tolerance = tolerance

    def check(self, actual: dict[str, float]) -> GateResult:
        violations = [
            GateViolation(
                metric=name,
                baseline=base,
                actual=actual.get(name, 0.0),
                tolerance=self._tolerance,
            )
            for name, base in self._baseline.items()
            if actual.get(name, 0.0) < base - self._tolerance
        ]
        result = GateResult(mode=self._mode, passed=not violations, violations=violations)
        if self._mode == GateMode.BLOCKING and violations:
            raise QualityGateError(result)
        return result
