# Glossary

Terms used throughout this documentation, defined once here instead of re-explained in every
file that uses them. Each entry links to the document where the concept is covered in full
depth — this page is a map, not a replacement for those documents.

## How to read this page

Entries are grouped by the part of the system they belong to: data, execution, security,
governance and evidence, assurance, integration, and quality. Within a group they are
alphabetical.

Three rules govern this page:

- **One definition per term.** This page is the canonical index for the project's vocabulary, and
  it does not outrank its own sources: where an entry disagrees with executable behaviour or an
  accepted ADR, those win and the entry is the thing to fix. Report the contradiction either way.
- **A definition states what exists, not what is intended.** Where a concept is defined by a
  contract but has no implementation behind it, the entry says so in those words.
- **Absent concepts are listed, not invented.** Section 8 separates what was removed, what was
  never here, and what is real but narrower than the word suggests, so that none of the three gets
  quietly reintroduced as an available capability.

The authority order that settles any remaining disagreement is in
[onboarding.md](onboarding.md), section 1.1.

---

## 1. Data

### Answer
The result of one pipeline request: `text`, a list of [Citation](#citation)s, an optional
`confidence`, the `model` that produced it, and a `trace_id` correlating it with the
[Trace](#trace--tracestep) of the request that built it. Defined in
`core/models/answer.py`. See [data-model.md](architecture/data-model.md), section 5.

### Chunk
A sub-segment of a [Document](#document), produced by a `Chunker`. Unlike `Document`, chunks are
mutable so an `Embedder` can write the embedding vector into them after creation. See
[data-model.md](architecture/data-model.md), section 2.

### Chunking
Splitting a document into smaller pieces before indexing, because embedding models and LLM
context windows both have practical size limits, and retrieval precision improves when a
chunk covers one coherent idea rather than an entire document. The framework ships
fixed-size and adaptive (section-aware) chunkers. See
[plugin-development.md](guides/plugin-development.md).

### Citation
A pointer from a generated `Answer` back to the specific `Chunk` that supports a claim in
it — includes the source, a verbatim excerpt, and a relevance score. See
[data-model.md](architecture/data-model.md), section 5.

### Classification (data classification)
The caller-supplied sensitivity level carried by a `Document` and propagated onto every `Chunk`
it produces: `public`, `internal`, `confidential`, or `restricted` (`core/enums.py`'s
`DataClassification`). **This codebase never infers it.** An unclassified value (`None`) is not
treated as `public`: a configured egress policy substitutes its own `default_classification`,
which is deny-by-default. Its first and current enforcement consumer is
[provider egress](#provider-egress); tenant-scoped filtering is a separate mechanism that does
not read this enum. See
[data-classification-policy.md](architecture/data-classification-policy.md).

### Document
The unit ingested into the pipeline: a `source`, its `content`, a `mime_type`, an owning
`tenant_id`, an optional [classification](#classification-data-classification), and metadata.
Frozen once created; chunking produces new objects rather than mutating it. Defined in
`core/models/document.py`. See [data-model.md](architecture/data-model.md), section 1.

### Query
One caller question: its `text`, its modality, an optional `tenant_id`, and metadata. Frozen
once created. The `tenant_id` is `None` until a caller authenticates; deny-by-default
enforcement of an unset value lives in the [tenant policy](#tenant-isolation), not in the model
itself. Defined in `core/models/query.py`.

### ULID (Universally Unique Lexicographically Sortable Identifier)
The ID format used for every entity in `core/models/` (`Document.id`, `Chunk.id`,
`Query.id`, etc.) — globally unique like a UUID, but sortable by creation time, which makes
debugging a chronological trace much easier than random UUIDs would.

---

## 2. Execution

### Agent
Historically, a specialized reasoning unit in a planned native multi-agent runtime
(coordinator, planner, retriever, extractor, synthesizer, validator). Per
[ADR-0005](adr/0005-document-ai-control-plane-boundary.md) §5.2 (accepted 2026-08-04), generic
multi-agent orchestration is now **delegated** to a selected external engine (LangGraph) via
the `DocumentEngine` port, not built as a native runtime — the five prototype classes above
were built once and removed in Lot 17 (`docs/refactoring-plan.md`) for having zero test
coverage and zero consumers. `src/modular_rag/agents/` today hosts only the adapter-integration
shell, not agent implementations. The selectable LangGraph adapter also runs a fixed RAG graph
today; selecting it does not activate multi-agent behaviour.
See [ROADMAP.md](../ROADMAP.md), V2, and `docs/refactoring/lot-17-prototype-retirement.md`.

### BM25 (Best Match 25)
A sparse, keyword-based lexical retrieval algorithm — ranks documents by term frequency and
inverse document frequency. Strong on exact terms and acronyms, blind to paraphrasing and
synonyms. Complements dense vector retrieval in the hybrid retriever. See
[structure.md](architecture/structure.md), `retrieval/retrievers/bm25.py`.

### Cross-encoder / Reranker
A model that scores a `(query, chunk)` pair directly (rather than comparing independent
embeddings), producing a more accurate but slower relevance score than a bi-encoder. Used to
re-score the top-k candidates after hybrid retrieval, before generation. See
[retrieval-methods.md](../examples/simple_qa/docs/retrieval-methods.md).

### Engine (`DocumentEngine`)
The vendor-neutral port through which a request is executed, defined in `contracts/engine.py`.
Two adapters implement it today: `NativeEngineAdapter`, which wraps the framework's own
`RAGEngine` pipeline, and `LangGraphEngineAdapter`, which runs a fixed
route → retrieve → guard → generate graph. A manifest selects one through `engine.adapter`.
Selecting an engine never changes which components are wired — both run against the same
`Container`. See
[document-engine-contract.md](architecture/document-engine-contract.md).

### Engine capability
A declaration by an engine adapter that it supports one optional behaviour: `streaming`,
`cancellation`, `tool_use`, `multi_turn`, or `governance_intercept` (`EngineCapability` in
`contracts/engine.py`). A caller must check `DocumentEngine.capabilities` before using a
capability-gated method; calling one that was not declared is a caller error, not something the
engine degrades silently. Today `NativeEngineAdapter` declares **none**, and
`LangGraphEngineAdapter` declares streaming, cancellation and governance intercept. **No shipped
adapter declares `tool_use` or `multi_turn`** — those members exist so a future adapter need not
extend the enum, not because the behaviour is available.

### GraphRAG
Retrieval-augmented generation that queries a knowledge graph (entities + relationships)
instead of, or in addition to, plain text chunks — enables multi-hop reasoning ("who is
affected, in cascade, by X?") that vector/BM25 search alone cannot answer. V3 scope. Per
[ADR-0005](adr/0005-document-ai-control-plane-boundary.md)/[ADR-0006](adr/0006-external-engine-selection.md),
the traversal itself is delegated to the selected external engine (LangGraph), not built as a
native retrieval path — see [Knowledge graph](#knowledge-graph-removed) in section 8: the native
graph data model that used to back this was removed entirely in Étape 8, so nothing
GraphRAG-related stays native today. See [onboarding.md](onboarding.md), section 3.

### Multi-hop reasoning
Answering a question that requires following more than one relationship (A relates to B,
which relates to C) rather than a single direct match — the reason V3 needs a knowledge
graph instead of only chunk-level retrieval.

### Reciprocal Rank Fusion (RRF)
An algorithm that merges independently ranked result lists using
`score(d) = Σ weight_i/(rrf_k + rank_i(d))`. This implementation exposes `rrf_k` and optional
per-list weights. It is chosen because it is
robust to the two lists having incomparable raw score scales. See
[overview.md](architecture/overview.md), section 11.

### Retriever
A component implementing `contracts/retrieval.py`'s `Retriever` Protocol —
`retrieve(query, k) → list[RetrievedChunk]`. Built-in implementations: `BM25Retriever`,
`VectorRetriever`, `PersistentSparseRetriever`, and `HybridRetriever` (which
fuses dense and lexical legs via RRF).

### VLM (Vision-Language Model)
A generator capable of taking both image and text input (e.g., Claude with vision, GPT-4V),
used in V5 to generate answers grounded in visual evidence (charts, scanned tables) rather
than only extracted text. No multimodal execution exists in this codebase today; per ADR-0005
§5.2 it is delegated, not a native build target.

---

## 3. Security

### Guard / SecurityGuard
A component that inspects a query before retrieval (`check_query()`) or an answer after
generation (`check_answer()`) for injection attempts, blocked terms, excessive length, or
policy violations. See [security.md](architecture/security.md).

### Identity (`TenantContext`)
The verified output of a [token verifier](#token-verifier): a `tenant_id`, a `user_id`, and a
set of [roles](#roles). Defined in `contracts/identity.py`. It is only ever constructed after a
token has been successfully validated — never hand-constructed to stand for an anonymous or
guest caller, because the fail-closed principle requires the **absence** of an identity to mean
denied, not a special empty one meaning allowed.

### PII (personally identifiable information)
Information that identifies a person. The shipped `PatternRedactor`
(`security/redaction/patterns.py`) replaces matches of a fixed pattern list — email addresses,
French phone numbers, IBANs, API-key-shaped strings, US social-security numbers, and
Luhn-valid card numbers — with `[REDACTED]`. **This is pattern matching, not a guarantee**: it
detects only what its patterns describe, it is not a classifier, and it does not cover every
jurisdiction's definition of personal data. Redaction of an answer also runs *after*
generation, so it cannot protect the [provider-egress](#provider-egress) boundary. See
[security.md](architecture/security.md).

### Policy / PolicyEngine
`Policy` (`core/models/policy.py`) is a named, tenant-scoped, ordered set of `PolicyRule`s,
each pairing a `condition` with a `PolicyAction` and a priority. `PolicyEngine`
(`security/policies/policy_engine.py`) is the broader rule-driven layer that evaluates them
before execution; it is hardened to fail closed. Distinct from
[tenant isolation](#tenant-isolation), which is the narrower always-on boundary, and from
[egress policy](#provider-egress), which governs what may leave for a remote provider. Roles do
not participate: see [Roles](#roles). See [ADR-0003](adr/0003-security-and-governance.md).

### Redaction
Replacing matched [PII](#pii-personally-identifiable-information) and secret patterns in text
with a placeholder. Wired as the optional `redactor` role and applied to an answer after
generation. It is a *safety* control, not a *security* one — the two must not be mixed, per
CLAUDE.md §07.

### Roles
The set of strings carried on a verified [identity](#identity-tenantcontext), extracted from
the token by the verifier and propagated through `ExecutionContext.roles` into the query path.
**Exactly one authorization decision reads them today.** `ApplicationService.record_feedback()`
rejects `is_test=True` unless the caller's verified roles contain `tester`, so synthetic feedback
cannot masquerade as real traffic in drift aggregation — it raises `SecurityError`, which the API
maps to HTTP 403 ([ADR-0014](adr/0014-feedback-drift-and-human-review.md), decision 6). Nothing
else branches on a role: there is no general resource-and-action RBAC, and no role governs
retrieval, generation, audit or administration. On the query path the roles are propagated and
never read. Treat any document describing broader role-based access decisions as describing
something not built.

### Tenant
The isolation boundary every governed request runs inside. A `tenant_id` is carried on
`Document`, `Chunk`, `Query` and `ExecutionContext`. The engine adapter treats the
`ExecutionContext` value as the single authoritative source and overwrites whatever the query
carried, rather than merging the two.

### Tenant isolation
The always-on fail-closed policy (`security/policies/tenant_isolation.py`) that denies a query
carrying no known tenant and filters retrieved chunks down to that tenant's own. It deliberately
contains no `try`/`except` that could turn an unexpected error into an allow. It is optional to
*configure* — a pipeline without it behaves as it did before the mechanism existed — but once
configured it never degrades open.

### Token verifier
The `TokenVerifier` Protocol (`contracts/identity.py`): verifies a bearer token and returns the
[identity](#identity-tenantcontext) it authenticates. It must raise on any invalid, expired or
unverifiable token, never return a placeholder identity as a fallback. The shipped
implementation is `KeycloakTokenVerifier` (`adapters/auth/`), which is an OIDC/JWKS client only —
the enforcement built on the verified identity lives in `security/policies/`.

---

## 4. Governance and evidence

### Audit event
Compliance evidence — who did what, to which tenant's data, when — recorded through an
`AuditSink` (`contracts/audit.py`). Deliberately separate from a [Trace](#trace--tracestep),
which is execution observability. Its payload is governed by an **allowlist**, not a denylist: a
new field must be added to `ALLOWED_PAYLOAD_KEYS` before it can reach audit storage, so a
sensitive value cannot leak in merely because nobody thought to exclude it. Event types cover
query receipt, retrieval, generation, guard decisions, egress decisions, and run success or
failure. See [ADR-0003](adr/0003-security-and-governance.md) and
[postgres-permissions.md](guides/postgres-permissions.md).

### Feedback
A caller-provided post-answer signal (`thumbs_up`, `thumbs_down`, optional redacted correction)
linked to `Answer.trace_id`. `Feedback` is distinct from an immutable `AuditEvent` and from a
pipeline-created `ReviewItem`. It is stored idempotently per tenant/key and consumed by offline
drift analysis. See [feedback-and-drift.md](guides/feedback-and-drift.md).

### Provider egress
Any transmission of query text, retrieved context, documents, embeddings, files, tool arguments,
or related customer data to a remote provider. Post-generation redaction does not protect this
boundary. The classification-aware, fail-closed check that runs immediately before an owned
component sends content outward is **implemented** (`contracts/egress.py`'s `EgressPolicy`, with
`security/policies/egress_policy.py`'s `ManifestEgressPolicy` as the reference implementation;
Lot 20, [ADR-0016](adr/0016-provider-egress-control.md)). It is enforced for the
framework's known remote provider types, all three runnable presets configure
`governance.egress_policy`, and each decision is content-free by construction so it can be
audited verbatim. It is not automatic: a pipeline that configures no egress policy behaves as it
did before the mechanism existed, the same way `tenant_policy` and `redactor` are not automatic.

### Trace / TraceStep
The execution trace of one pipeline request (distinct from the compliance `AuditEvent` stream).
The query guard, retrieval, optional reranker, and generator append `TraceStep` records; tenant
and policy checks, post-generation guarding, redaction, and human review do not yet have their
own named steps. `add_step()` updates running totals, and `Answer.trace_id` provides correlation.
See [data-model.md](architecture/data-model.md), section 6, and
[observability.md](guides/observability.md) for the exact coverage.

### Tracer / Meter
`Tracer` is the live distributed-span port introduced by ADR-0012. `Meter` is the separate
operational counter/histogram/gauge port introduced by ADR-0013; it is not the evaluation
`core.models.Metrics` bag. Both are optional manifest roles with OTel and null implementations.
No shipped preset enables them today.

---

## 5. Assurance and the external-application boundary

### Assurance level
Three compatibility profiles defined by [ADR-0015](adr/0015-portable-assurance-and-external-application-boundary.md)
§3 and made machine-checkable by [ADR-0017](adr/0017-engine-independent-assurance-contract.md):
**L0** (opaque request/response boundary), **L1** (evidence-aware — provenance and identity can
be checked), **L2** (governed stages — egress, policy, audit completion, review routing can be
enforced). The contract is **implemented** (`contracts/assurance.py`) and both shipped engine
adapters compute a report. An adapter cannot assert its own level: `achieved_level` is a
computed property derived only from the [evidence](#evidence) entries, by one pure function.
The levels exist to stop a limited external adapter from being described as having
native-equivalent guarantees.

### Conformance report
An engine adapter's deterministic, machine-readable assurance report for one execution
(`ConformanceReport` in `contracts/assurance.py`). It must carry exactly one
[evidence](#evidence) entry per evidence kind — a report that omits a kind is rejected at
construction, because a silent omission is precisely the gap this contract exists to expose.

### Control point
Where a framework-owned control can attach to a foreign application: request admission,
retrieval result, pre-model egress, tool invocation, stream chunk, or result admission
(`ControlPoint` in `contracts/application.py`,
[ADR-0018](adr/0018-existing-application-adapter-boundary.md)). Only request admission and result
admission are structurally guaranteed, because the adapter owns the call itself. Every other
point exists **only if the application genuinely exposes a hook** — a callback, middleware, event
or interface — never something inferred from observed behaviour, log parsing or heuristics. How
firmly a control attaches is graded separately by `ControlPointSupport`
(`unavailable` < `observed` < `enforced`). This is contract vocabulary only: see
[Existing-application adapter](#existing-application-adapter-contract-only-no-implementation).

### Evidence
What an adapter reports about one execution so that a claim can be graded rather than trusted.
An evidence entry pairs a **kind** — identity/tenant, retrieval provenance, egress decision,
policy decision, audit completion, usage and cost, feedback and review routing, streaming
pre-validation — with a **status**. The four statuses are ordered and deliberately not collapsed
into a boolean:

| Status | Meaning |
|---|---|
| `unsupported` | The adapter has no mechanism for this kind under this wiring. |
| `observed` | The adapter reported it; the framework did not independently check it. |
| `verified` | The framework's own code checked it. |
| `enforced` | The framework's own code can block on it. |

`observed` must never be promoted silently to `verified` or `enforced`. Retrieval provenance,
for instance, reaches `verified` only when the framework itself confirms that each citation's
displayed passage, source and page really belong to a chunk that was retrieved for that request —
reusing a real chunk id while fabricating the passage yields `observed`, not `verified`. Defined
in `contracts/assurance.py`.

### Existing-application adapter (contract only, no implementation)
The boundary for wrapping an application the framework did not build
([ADR-0018](adr/0018-existing-application-adapter-boundary.md), Lot 22). **Only the contract
exists** (`contracts/application.py`): there is no `adapters/applications/` package and no
manifest can select such an adapter. Wrapping an existing application is not a current
capability and must never be described as operational. The contract's purpose is to cap what
such an adapter could claim — an application's declared [control points](#control-point)
determine a ceiling on the [evidence](#evidence) statuses, and therefore on the
[assurance level](#assurance-level), it can reach.

---

## 6. Integration and extension

### Adapter
A concrete binding to an external library or service (OpenAI, Qdrant, HuggingFace) that
implements a `contracts/` Protocol. Adapters live under `adapters/` specifically so that
domain modules don't need the heavy external dependency installed to be unit-tested. See
[module-model.md](architecture/module-model.md).

### ComponentRegistry
The object that maps a `(role, type_name)` pair (e.g., `("chunker", "adaptive")`) to a
factory function that builds the concrete instance. Populated by
`app/default_factories.py`, consumed when a manifest is wired into a `Container`.
See [overview.md](architecture/overview.md), section 9.

### Contract
A `typing.Protocol` in `src/modular_rag/contracts/` that defines the interface a capability
must satisfy (e.g., `Chunker`, `Retriever`, `Generator`). Chosen over abstract base classes
so that third-party implementations never need to import or subclass anything from this
framework. See [ADR-0002](adr/0002-contracts-and-plugins.md).

### Domain module
One of `ingestion/`, `retrieval/`, `generation/`, `security/`, `eval/`, `memory/`,
`observability/` — implements one capability, depends only on `contracts/` + `core/models/`,
and must never import from another domain module. `agents/` is no longer a domain module in
this sense: per ADR-0005 §5.2, it hosts only engine-delegation adapter integration (not yet
built), not a capability implementation of its own. See
[module-model.md](architecture/module-model.md).

### Hexagonal architecture
The layering discipline this framework enforces: outer layers depend inward
(`cli`/`api` → `app` → `orchestration` → contracts/core, with domains and adapters implementing
or consuming inward contracts), so
any component can be swapped by implementing its Protocol, without the rest of the system
needing to change. See [ADR-0001](adr/0001-modular-architecture.md).

### Manifest
A YAML file describing a complete pipeline configuration — which chunker, embedder,
retriever, reranker, generator, guard, governance/lifecycle adapters, telemetry, tracer and meter
to use, and with what parameters. It is the source of truth for runtime pipeline components.
Bearer-token verification and file-parser dispatch are explicit application/ingestion exceptions.
See [manifests/_index.md](../manifests/_index.md).

---

## 7. Quality and evaluation

### Benchmark
An offline run of a [golden set](#golden-set) against a wired pipeline, producing a
`BenchmarkReport` (`eval/runners/benchmark.py`). It separates a case that *failed* — the engine
call itself raised — from a case that ran and scored zero, and classifies each failure by stage:
retrieval, generation, security, or infrastructure. Safety-probe cases are scored separately
from question-answering cases. Per [ADR-0008](adr/0008-offline-evaluation-and-engine-activation.md)
the benchmark is script-driven and never manifest-activated.

### Golden set
A versioned, named collection of benchmark cases with an optional corpus to ingest first
(`GoldenSet` in `eval/runners/benchmark.py`). It carries a schema version and a domain label so
that a run is a comparable artifact — "did this domain's golden set regress" — rather than an
anonymous list. One populated dataset ships today (`eval/datasets/core_v1.yaml`, domain
`default`). See [offline-evaluation.md](guides/offline-evaluation.md).

### Groundedness
A measure of how well an answer's claims are supported by the retrieved context, typically
computed as token overlap between the answer and the source chunks. Used as an evaluation
metric (`generation/validators/groundedness.py`). See
[data-model.md](architecture/data-model.md), section 8 (`Metrics`).

### Quality gate
The comparison of measured metrics against a recorded baseline (`eval/quality_gate.py`). In
`report_only` mode it never raises and the caller inspects the result; in `blocking` mode it
raises on any violation past tolerance. It fails closed in both directions: a metric missing
from the actual results counts as `0.0` where higher is better, and as infinity for a metric
declared `lower_is_better`, so an absent reading looks like a regression rather than a perfect
score. Enforced in CI by the `benchmark-gate` job.

### Regression
In evaluation, a metric that has moved past its tolerance in the wrong direction relative to the
baseline — what a [quality gate](#quality-gate) reports as a violation. In testing, the broader
sense of previously working behaviour that a change has broken; the validation tiers that detect
it are in [validation-protocol.md](guides/validation-protocol.md). The two senses are related but
not interchangeable: a quality-gate regression is a measured metric movement, not a failing test.

---

## 8. Removed, absent, and overstated terms

### 8.1 Removed — kept only for historical traceability

These existed in this codebase and were deleted. They are recorded so that a reference found in
an old document or commit can be resolved, not because they are roadmap capabilities.

#### EvoRAG (removed)
Historical name for a removed prototype that strengthened or weakened knowledge-graph edges
based on answer outcomes. Its implementation
(`GraphVersionManager.reinforce()`/`weaken()`/`prune()`, `memory/versioning/`) was removed in
Lot 17 (`docs/refactoring-plan.md`) — zero test coverage, zero consumers, and squarely in the
delegated fine-tuning-execution territory ADR-0005 §5.2 assigns to the external engine. The
name is retained only for historical traceability; it is not a current roadmap capability.

#### Knowledge graph (removed)
Historically, a graph of entities (`GraphNode`) and typed relationships (`GraphEdge`), modeled
in `memory/graph/knowledge_graph.py` as a plain Python dict/list (despite an earlier version of
that module's own docstring, it never used NetworkX). Lot 17 initially kept this class with a
documented "undecided" caveat — its `neighbours()`/`subgraph_for_query()` methods were genuine
multi-hop-traversal logic, exactly the capability
[ADR-0005](adr/0005-document-ai-control-plane-boundary.md) §5.2 delegates to the external
engine, which made "keep as a passive native data model" hard to justify. Étape 8
([ADR-0007](adr/0007-layer-boundaries-and-control-plane-activation.md)) resolved that
undecided caveat: the class was **removed entirely** (zero consumers anywhere outside its own
test), along with `core.enums.GraphRelation`. `memory/graph/` is empty today, restorable via git
history if a real, wired need emerges. See [structure.md](architecture/structure.md).

### 8.2 Never part of this project

These terms appear in adjacent products and in generic RAG writing. No contract, manifest, ADR or
module defines them here, and none ever did, so they must not be used in this project's
documentation as if they existed.

| Term | Why it is not used here |
|---|---|
| Conversation, session | The pipeline answers one `Query` at a time, with nothing storing or replaying a caller's prior turns and no adapter declaring `multi_turn`. |
| Benefits mode | Not a concept in any contract, manifest, ADR or module. |

### 8.3 Real, but routinely overstated

Unlike section 8.2, each term below names something this project genuinely has a position on. What
makes them worth listing is that the position is narrower than the term normally implies. The
status labels are the project's own capability vocabulary: *narrowly implemented*, *delegated*,
*contract-only*, *planned*.

| Term | Status | What is actually true |
|---|---|---|
| Role-based access decision (RBAC) | Narrowly implemented | The only role gate is the `tester` check on synthetic feedback; see [Roles](#roles). |
| Agent team, planner, synthesizer | Delegated; prototypes removed | The native prototypes were deleted in Lot 17 and generic orchestration is delegated per ADR-0005 §5.2. |
| Tool-using agent | Delegated; not declared | No shipped adapter declares the `tool_use` [engine capability](#engine-capability), and the LangGraph graph is fixed. |
| Application wrapping | Contract-only | ADR-0018 is accepted and `contracts/application.py` ships, but no adapter exists and no manifest can select one. |
| Compliance report (GDPR, HIPAA, CCPA) | Planned | The [audit event](#audit-event) stream is implemented; formatted regulatory reports and lineage tracking are not built. |
