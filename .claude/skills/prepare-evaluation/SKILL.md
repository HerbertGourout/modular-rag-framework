---
name: prepare-evaluation
description: Prepare or extend the repository's offline golden-set benchmark and quality gate
---

# Prepare Evaluation

Use this workflow to add evaluation cases, metrics, reports, or release thresholds. The shipped
evaluation system is offline and programmatic by design (ADR-0008); it is not a runtime manifest
component and it must not call a paid or remote model during the default CI job.

## Read first

- `docs/research/DIGEST-evaluation.md`
- `docs/guides/offline-evaluation.md`
- `src/modular_rag/eval/datasets/core_v1.yaml`
- `src/modular_rag/eval/datasets/loader.py`
- `src/modular_rag/eval/runners/benchmark.py`
- `src/modular_rag/eval/quality_gate.py`
- `scripts/run_benchmark.py`

Do not invent a second dataset schema, runner, report model, or threshold mechanism. Extend the
existing types and their tests.

## Current evaluation surface

- Golden cases: `eval/datasets/core_v1.yaml`, loaded by `load_golden_set()`.
- Runner: `BenchmarkRunner`, operating through the engine-facing evaluation contract.
- Scorers: exact match, retrieval metrics including NDCG, faithfulness, and answer correctness.
- Reports: deterministic serialization in `eval/reporting.py`.
- Release decision: `QualityGate` and the committed baseline.
- CI entry point: `python scripts/run_benchmark.py --enforce`.
- Deliberate baseline update: `python scripts/run_benchmark.py --update-baseline`.
- Drift: a separate operational signal, run with `scripts/run_drift_check.py`; feedback and drift
  do not silently rewrite the golden set or release baseline.

## Workflow

### 1. State the behavior being protected

Identify the changed retrieval, generation, governance, or scoring behavior. Select a metric that
measures that behavior directly. Cite the evaluation digest when introducing or changing a metric.

### 2. Extend the golden set

Add the smallest representative cases to `core_v1.yaml` using its existing schema. Keep stable,
valid index identifiers for documents and chunks; readable labels may live in descriptive fields.
Every expected answer and relevance judgment must be human-reviewed. Do not encode production
secrets, personal data, or customer content in the repository fixture.

### 3. Reuse or extend a scorer

Prefer an existing scorer. If a new metric is necessary:

1. implement it under `src/modular_rag/eval/scorers/`;
2. specify edge cases such as empty relevance sets and zero-result retrieval;
3. add unit tests for the formula and aggregation behavior;
4. expose it through the existing benchmark report rather than a parallel result format.

Aggregate retrieval scores can hide regressions between semantic strata. When the dataset contains
meaningful categories, report the relevant slice as well as the aggregate.

### 4. Run the benchmark without changing policy

```powershell
.\.venv\Scripts\python.exe scripts\run_benchmark.py
```

Inspect the generated report and explain material changes. A failing score is evidence to
investigate, not permission to lower a threshold.

### 5. Update the baseline only with explicit justification

Use `--update-baseline` only when the behavior change and expected score movement have been
reviewed. Commit the baseline change with the implementation, dataset, tests, and explanation.
Never update a baseline merely to make CI green.

### 6. Validate the gate

```powershell
.\.venv\Scripts\python.exe scripts\run_benchmark.py --enforce
.\.venv\Scripts\python.exe -m pytest tests\unit\eval tests\contract -q
```

Use the repository's actual test paths if the affected test is more specific. Do not run optional
provider-backed integration tests without confirmed services and credentials.

## Completion criteria

- The new or changed case exercises the intended behavior.
- Metrics use the repository implementations and documented semantics.
- The report remains deterministic and contains no sensitive text.
- Threshold changes, if any, are explicit and justified.
- Offline benchmark and affected unit/contract tests pass.
- Documentation describes measured results as results, not as market or compliance guarantees.
