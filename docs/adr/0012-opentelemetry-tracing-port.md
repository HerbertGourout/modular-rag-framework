# ADR-0012 — OpenTelemetry Tracing via a New `Tracer` Port

**Status:** Accepted
**Date:** 2026-08-19
**Authors:** Claude Code (implementation), reviewed via the project's Codex handoff process

---

## Context

Lot 11 (external plan — "OpenTelemetry"; **not** this repository's own `docs/refactoring-plan.md`
Lot 11a/b/c sequence, which is unrelated, already-completed tenant-isolation/redaction/audit work
— see the numbering-collision convention established in earlier external-plan Lots) asks for
effective OpenTelemetry instrumentation across the API, ingestion, embedding, retrieval,
reranking, and generation stages, with `correlation_id`/`request_id`/`trace_id` propagation, a
toggleable OTLP exporter, safe (non-PII) span attributes, and no functional impact when the
exporter is unavailable.

The existing `Telemetry` Protocol (`contracts/telemetry.py`) is post-hoc only —
`record_trace(trace: Trace)` receives a fully-built `Trace` after a run completes.
`TraceStep` (`core/models/trace.py`) has no start/end timestamps and no parent/child
relationship, so it cannot be losslessly translated into real, correctly-nested OTel spans
with accurate wall-clock timing. Live span creation (start now, attach attributes as the
step executes, end when it completes) is required to satisfy "a consistent distributed
trace for a request."

`pyproject.toml`'s `v4` optional dependency group already declares
`opentelemetry-sdk`/`opentelemetry-api`/`opentelemetry-exporter-otlp` (>=1.24), unused by any
code today (confirmed: zero `opentelemetry` imports anywhere in `src/`/`tests/` before this
change) — this ADR is the first time they are actually wired in.

Per `.claude/.instructions.md` §7 and `CLAUDE.md` §05 item 7, all domain modules
(`ingestion/`, `retrieval/`, `generation/`, `security/`, `agents/`, `memory/`, `eval/`) may
import only `contracts/` + `core/models/` — never a third-party library directly, and never
each other. The task itself repeats this explicitly: "avoid any domain dependency on
OpenTelemetry."

## Decision

1. **A new, additive Protocol** in `contracts/tracing.py`: `Tracer`/`Span`, framework-neutral
   (no OpenTelemetry types appear in the Protocol signatures — mirrors `contracts/engine.py`'s
   `EngineStep` being "shape-compatible... without the engine needing to know our type").
   This is a **new** contract, not a modification of the existing `Telemetry` Protocol — per
   `contracts/CLAUDE.md`'s own worked example ("✅ ALLOWED: New Protocol in new version...
   implementations opt-in"), this does not require migrating any existing `Telemetry`
   implementer. `Telemetry` (post-hoc trace/metrics recording) and `Tracer` (live span
   creation) stay deliberately separate, mirroring the existing, already-established
   separation between `Telemetry` and `AuditSink` (`docs/guides/observability.md`).

2. **`NullTracer`/`NullSpan`** (`observability/__init__.py`, alongside the existing
   `NullTelemetry`) are the true no-op implementation — this is what "instrumentation can be
   disabled" resolves to: omit `observability.tracer` from a manifest (or explicitly select
   `type: null`) and zero spans are ever created, matching the `telemetry: type: null`
   precedent exactly.

3. **`OtelTracer`** (`adapters/observability/otel_tracing.py`, a new adapter subpackage,
   following the `adapters/{audit,auth,embeddings,lifecycle,llms,postgres,vectorstores}/`
   precedent) is the real implementation. It lazy-imports every `opentelemetry.*` symbol
   inside method bodies only, never at module level, per the mandatory lazy-import rule for
   optional heavy dependencies. It wraps OpenTelemetry's own
   `Tracer.start_as_current_span()` context manager so span nesting/parenting uses
   OpenTelemetry's real context-propagation machinery (Python `contextvars`), not a
   hand-rolled parent/child scheme — this is what makes "a consistent distributed trace for a
   request" correct for free: every layer that receives the *same* `Container`-registered
   `OtelTracer` instance and creates a span from within the same call stack automatically
   nests under whatever span is currently active, with zero explicit ID threading required
   between `app/`, `orchestration/`, and `api/`.

4. **Export is toggled by whether an OTLP endpoint is configured**, not by a separate on/off
   flag duplicating that information: `OtelTracer(otlp_endpoint=None)` (the default) creates
   real spans — so every attribute-setting/error-recording code path is still exercised
   uniformly in every environment — but attaches no span processor that talks to a network
   endpoint, so nothing is ever transmitted. Setting `otlp_endpoint` attaches a
   `BatchSpanProcessor(OTLPSpanExporter(...))`; OpenTelemetry's own `BatchSpanProcessor`
   exports asynchronously on a background thread and swallows/logs export failures
   internally rather than propagating them to instrumented application code — this is the
   mechanism satisfying "no functional impact if the exporter is unavailable," not new code
   this adapter has to build itself. A dedicated `OtelTracer.for_testing()` constructor wires
   an in-process `InMemorySpanExporter` via a `SimpleSpanProcessor` (synchronous, so tests can
   assert on finished spans without a sleep/poll) instead of the OTLP path — this is the
   "test using an in-memory exporter" requirement.

5. **`Container.tracer` follows the established `X | None` + `.get()` optional-role pattern**
   (`reranker`, `guard`, `telemetry`, `audit_sink`, `tenant_policy`, `redactor`,
   `review_queue`, `lifecycle_ledger`, `policy_engine`) — **not** a "default to a
   `NullTracer()` singleton when unregistered" pattern. This is a deliberate rejection of an
   alternative that would have removed the need for an `if self._c.tracer:` guard at every
   call site: introducing a *third* container-property convention (after `_get()`-raises and
   `.get()`-returns-None) risks exactly the kind of asymmetry defect this project already paid
   for once (Batch 10/external-plan, `IndexReconciler`'s `retriever` role — see
   `.claude/rules/health-checks.md` for the parallel "don't repeat a solved problem" lesson
   from `check_health()`'s five-round history). The nine existing precedents for this exact
   pattern have zero recorded incidents; `tracer` follows them exactly.

6. **Instrumentation sites are added only in `orchestration/engine.py`, `app/application.py`,
   and `api/__init__.py`** — never inside `ingestion/`, `retrieval/`, `generation/`,
   `security/`, or `adapters/embeddings/`. "Instrument ingestion, embedding, retrieval,
   reranking, generation" is satisfied by wrapping the *call sites* of those stages from the
   orchestration layer (`RAGEngine.ingest()`/`ingest_chunks()`/`_run_steps()`), exactly
   mirroring how `TraceStep` emission already works for retrieve/rerank/tenant_filter today
   (only the generator self-instruments its own `TraceStep`; this ADR does not add
   self-instrumentation to generators either, for the same domain-dependency reason — the
   *span* wrapping it lives in `orchestration/`, not inside the generator).

7. **`ObservabilitySection.tracer: ComponentConfig | None = None`** is added to
   `contracts/manifests.py` as a new optional field with a default — backward compatible with
   every existing manifest (`extra="forbid"` blocks unknown *keys*, not new optional fields
   with defaults). This is a `BaseModel` addition, not a `Protocol` change, so it does not fall
   under `contracts/CLAUDE.md`'s "never change a Protocol without an ADR" rule on its own; it
   is recorded here because it is part of this ADR's overall decision, not because the field
   addition alone would need one.

8. **`engine.adapter: "langgraph"` manifests that also set `observability.tracer` are accepted
   at `wire()` time** — corrected during this ADR's own review cycle (Codex pass-1 HIGH-001):
   an earlier version of this decision rejected the combination, copying the
   `observability.telemetry`/`governance.audit_sink`/`governance.policy_engine`/
   `governance.review_queue` rejection pattern (`orchestration/registry.py::
   runtime_manifest_errors()`) without checking whether it applied for the same reason. It does
   not: `Container.tracer` is read directly by `app/application.py`'s `"app.request"` span and
   `api/__init__.py`'s `"api.answer"`/`"api.retrieve"` spans, both engine-neutral and
   unconditional on which `DocumentEngine` is selected — unlike `telemetry`/`audit_sink`/
   `policy_engine`/`review_queue`, which are read only from inside `RAGEngine`, never reached at
   all under `engine.adapter: "langgraph"`. ADR-0008's actual concern ("a selected engine must
   never silently ignore a declared control") does not apply: the declared tracer genuinely *is*
   consulted, at those two engine-neutral boundaries. Only `RAGEngine`-internal spans (`rag.answer`,
   `rag.guard_query`, ...) are unavailable under LangGraph — a narrower, already-documented scope
   boundary (this ADR's own "LangGraphEngineAdapter internal step instrumentation" note below),
   not a case of a declared control being ignored.

9. **PII safety**: span attributes are restricted to counts, latencies (implicit via span
   timing), status, provider/model identifiers (`Component.name()`, already a non-secret,
   already-logged identifier throughout this codebase), and the three propagated ids
   (`correlation_id`, `request_id`, the OpenTelemetry-native `trace_id`/`span_id`). No query
   text, document content, answer text, or token content is ever passed as a span attribute —
   the same allowlist discipline `orchestration/CLAUDE.md`'s existing `TraceStep` checklist
   already establishes ("NEVER: full query text... NEVER: full answer text") applies
   identically here.

## Explicitly out of scope for this ADR

- **Cross-service W3C `traceparent` header extraction/injection** at the API boundary. This
  ADR's distributed-trace guarantee is same-process (all instrumented layers share one
  `Container`-registered `OtelTracer`, nested via `contextvars`); accepting an inbound
  `traceparent` from an upstream caller (or emitting one for a downstream call) is a real,
  separate extension that would require extending the `Tracer`/`Span` Protocol with
  context-extraction/injection methods no other consumer needs today. Deferred as a known
  limitation, not silently assumed solved.
- **Unifying `Trace.id`, `ExecutionContext.correlation_id`/`request_id`, and OpenTelemetry's own
  trace_id into a single identifier.** All three continue to exist as distinct concepts; this
  ADR propagates all three as span attributes on the same spans (satisfying the literal "propagate
  correlation_id, request_id, and trace_id" requirement) rather than collapsing them into one,
  which would be a larger, separately-scoped refactor touching `api/errors.py`'s own ad-hoc
  correlation id, `AuditEvent.correlation_id`, and `Answer.trace_id` simultaneously.
- **`LangGraphEngineAdapter` internal step instrumentation.** ADR-0005 §5.2 delegates generic
  orchestration mechanics to the external engine; this ADR instruments the native pipeline and
  the engine-neutral `ApplicationService`/`api/` boundary (which covers a LangGraph-routed
  request with one root span each), not LangGraph's own internal step graph.
- **`opentelemetry-instrumentation-fastapi` or any other auto-instrumentation package.** Not
  declared in `pyproject.toml` today and not required to satisfy the task; adding it would be a
  new dependency the task does not explicitly authorize. API-layer spans are created manually
  via the same `Tracer` Protocol every other layer uses, for consistency and testability with
  the in-memory exporter.
- **`cli/` instrumentation.** Not named in the task's explicit list (API, ingestion, embedding,
  retrieval, reranking, generation); `RAGEngine.ingest()`/`ingest_chunks()` still gain spans
  regardless of caller (CLI or otherwise), since the spans live in `orchestration/`, not `cli/`.

## Consequences

**Positive:**
- A single request produces one real, correctly-nested OpenTelemetry trace spanning
  API → application → orchestration stages, exportable to any OTLP-compatible backend
  (Jaeger, Tempo, Grafana, Honeycomb, etc.) without further code changes.
- Zero new required dependencies (the `v4` group already declared what's needed) and zero
  behavior change for any manifest that doesn't opt in.
- Domain modules remain fully decoupled from OpenTelemetry, preserving `CLAUDE.md`'s hexagonal
  layering guarantee and the task's explicit "avoid any domain dependency" requirement.

**Negative / accepted risk:**
- Two "correlation id" propagation mechanisms now coexist without being unified
  (`ExecutionContext.correlation_id`/`request_id` as span attributes, plus OpenTelemetry's own
  native trace/span ids) — documented above as a deliberate, separately-scoped deferral, not an
  oversight.
- No cross-service trace continuity (a caller's own `traceparent` is not honored) until the
  deferred extension above is built.

## References

- [docs/refactoring/technology-candidates.md](../refactoring/technology-candidates.md) — prior
  design note: "TraceStep should emit OTel-compatible spans instead of a proprietary format."
- [.claude/rules/health-checks.md](../../.claude/rules/health-checks.md) — the precedent this
  ADR's `Container.tracer` design explicitly avoids repeating.
- [ADR-0008](0008-offline-evaluation-and-engine-activation.md) — "a selected engine must never
  silently ignore a declared control," applied here to `observability.tracer` under the
  LangGraph adapter.
- [docs/guides/observability.md](../guides/observability.md) — updated with the new tracing
  section as part of this change.
