# ADR-0008 — Offline evaluation and honest engine activation

**Status:** Accepted
**Date:** 2026-08-08

## Context

`ExactMatchEvaluator` requires an expected answer and `QualityGate` compares aggregate metrics
with a recorded baseline. Normal production questions provide neither a gold answer nor a
golden dataset. Wiring these objects into a container did not make them part of online answer
execution, even though the secure preset and capability matrix described a blocking runtime
gate.

The LangGraph adapter consumes the security guard, tenant policy and redactor, but does not yet
consume the policy engine, audit sink, review queue or telemetry. Accepting those declarations
would make a manifest claim controls that never execute.

## Decision

1. Exact-match evaluation and baseline quality gates remain native, programmatic offline
   evaluation capabilities. They are not online pipeline components.
2. Runnable pipeline manifests must not declare `evaluation` or `quality.gate` until a dedicated
   manifest-driven evaluation runner consumes them. Startup and direct registry wiring reject
   such declarations instead of silently constructing unused objects.
3. `engine.adapter: langgraph` rejects policy-engine, audit-sink, review-queue and telemetry
   declarations until those controls move above the engine boundary or the adapter consumes
   them with conformance tests.
4. `load_pipeline()` rejects delegated engine selections. Callers must use `load_engine()` or
   `load_application()` so an engine choice can never silently fall back to native.

## Consequences

- The secure runtime preset no longer claims a blocking exact-match gate.
- Regression gates remain usable through `eval/` and golden-set tooling, where expected answers
  exist and blocking has a well-defined meaning.
- Engine-specific limitations fail during startup and manifest validation.
- Adding online quality enforcement later requires an online metric with no gold dependency, a
  stable contract, manifest activation and semantic conformance tests for every supported
  engine.
