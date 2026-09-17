---
paths:
  - "src/modular_rag/orchestration/**/*.py"
description: "Rules for registry wiring, native execution, engine adapters, and state transitions"
version: "3.0"
lastUpdated: "2026-09-02"
---

# Orchestration rules

Read `src/modular_rag/orchestration/CLAUDE.md` and the affected contracts before editing this
layer. Orchestration may import only `core`, `contracts`, and `orchestration`; concrete component
imports belong in the `app/` composition root.

## 1. Wiring

- `ComponentRegistry` maps `(role, type_name)` to a factory and wires a `PipelineManifest` into a
  `Container`.
- Register built-ins only in `src/modular_rag/app/default_factories.py`.
- Select built-ins through YAML manifests; do not instantiate concrete domains/adapters inside
  orchestration.
- Update `app/config_resolution.py` and registry validation when an engine cannot consume a
  declared control. Unsupported declarations must fail before execution, not become silent no-ops.

## 2. Native engine flow

`RAGEngine.answer()` builds a `Query` and runs the fixed sequence implemented by `_run_steps()`:

1. tenant identity enforcement;
2. policy enforcement;
3. query guard;
4. retrieval;
5. tenant chunk filtering;
6. optional reranking;
7. generation;
8. answer guard;
9. redaction;
10. optional human-review queueing.

Any flow change must preserve fail-closed governance, update state-machine transitions when
needed, and have focused tests. Generators emit their own `TraceStep`; do not add a second
overlapping generation step that double-counts latency.

`RAGEngine.retrieve()` is a separate, narrower operation and returns `RetrievalResult` with chunks
and a framework trace id. `record_feedback()` is also separate and requires a configured sink; a
non-empty correction requires redaction before persistence.

## 3. Engine boundary

The `DocumentEngine` port makes execution replaceable. The native engine remains the reference
implementation. `LangGraphEngineAdapter` is optional and supports a bounded subset of container
controls; it does not define the repository architecture.

Current LangGraph parity covers tenant isolation, `SecurityGuard`, and redaction. Manifests using
native-only policy, review, audit, feedback, or post-hoc telemetry roles are rejected. A new
adapter must declare capabilities honestly and pass semantic/conformance tests for every claimed
capability.

Generic multi-agent planning and arbitrary application orchestration are delegated through the
engine boundary per ADR-0005. Do not recreate the retired `QueryRouter` or `FlowCompiler` without
a new accepted decision and a concrete consumer.

ADR-0015's L0/L1/L2 external-application assurance boundary is accepted; its cross-engine
conformance report (Lot 21, ADR-0017) and provider-egress authorization (Lot 20, ADR-0016) are
both implemented and enforced. Only the existing-application adapter itself (Lot 22 —
`adapters/applications/`) remains unimplemented; its contract (`contracts/application.py`)
already exists.

## 4. Tracing, metrics, and audit

- Use the real `TraceStep(name, input_tokens, output_tokens, latency_ms, metadata)` fields.
- Never place raw sensitive text, secrets, or provider payloads in traces, spans, metrics, logs,
  or public readiness errors.
- Request-level OTel spans/metrics live at application/API boundaries; native stage spans and
  metrics live in `RAGEngine`. Avoid duplicate emission.
- Preserve failure traces and audit evidence before propagating an exception.
- Audit storage receives redacted query text only when a redactor is configured; otherwise the
  text is omitted.

## 5. Error and availability semantics

- Do not swallow component failures unless the concrete component contract defines a tested
  degradation path, such as hybrid retrieval fallback.
- Mandatory governance and tenant controls fail closed.
- Readiness criticality must match actual query-serving behavior; update readiness tests if a new
  component can make `answer()` or `retrieve()` unavailable.
- Shutdown remains best-effort per component and must not prevent other resources from closing.

## 6. Validation

For orchestration-sensitive changes run, at minimum:

```powershell
.\.venv\Scripts\python.exe scripts\check_layering.py --strict
.\.venv\Scripts\python.exe -m pytest tests\unit\orchestration tests\contract -q
```

Also run relevant app/bootstrap, manifest, API, adapter, governance, and parity tests. Use the
actual test paths present in the repository. Do not run provider-backed integration tests without
confirmed services and credentials.

## Checklist

- [ ] No concrete domain/adapter import in orchestration.
- [ ] New built-in registered in `app/default_factories.py` and selected by manifest.
- [ ] Unsupported engine/control combinations fail during validation.
- [ ] Native and claimed adapter semantics have focused parity tests.
- [ ] No duplicated trace/span/metric or sensitive metadata.
- [ ] State, audit, readiness, and failure semantics remain coherent.
- [ ] Documentation distinguishes current behavior from Lots 20–22 proposals.
