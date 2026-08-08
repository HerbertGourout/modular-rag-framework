# ADR-0007 — Layer Boundaries and Control-Plane Activation

**Status:** Accepted  
**Date:** 2026-08-07  
**Authors:** Codex, from the repository-wide alignment audit requested by Herbert Gourout

---

## Context

ADR-0005 established the engine-independent control plane — governance, audit, evaluation,
tenant isolation, configuration, and portability — as this package's durable product boundary.
ADR-0006 selected LangGraph as the first external orchestration engine behind `DocumentEngine`.

The implementation contains the required primitives, but two structural gaps prevent the
repository from matching that boundary:

1. The published dependency direction says `api/cli → app → orchestration → contracts/core`,
   while `orchestration/engine.py`, `registry.py`, and `reconciliation.py` import
   `app.Container`. API and CLI also import contracts, core models, and domain code directly.
2. Governance, audit, redaction, tenant isolation, lifecycle, telemetry, review, and quality
   implementations are normally activated by direct Python injection. Their V2 manifest
   sections are parsed but not consumed by `ComponentRegistry.wire()`.

The former layering audit did not report the first gap because it enforced rules only for
core, contracts, domain, and adapter packages. The evidence snapshot is recorded in
[the capability matrix](../architecture/capability-matrix.md).

---

## Decision

Accepted by the project owner on 2026-08-07 with authorization to execute the
remaining correction and refactoring plan through completion.

### 1. Make orchestration own the runtime component container

Move `Container` from `app/container.py` to `orchestration/container.py`.

- `orchestration` may import only `core`, `contracts`, and its own package.
- `app` composes orchestration and process-level concerns.
- A temporary `app.container` compatibility re-export may be kept for one pre-alpha migration
  window if tests or documented callers require it.

This location matches actual ownership: `ComponentRegistry` creates the container and both
native and external engine adapters consume it.

Move the concrete built-in composition function from
`orchestration/_default_factories.py` to `app/default_factories.py`. The generic registry stays
in orchestration; the application composition root is the one place allowed to know concrete
domain and adapter implementations.

### 2. Put a service facade between interfaces and implementation details

`api/` and `cli/` may import only their own package plus a public application facade. The facade
owns:

- loading and resolving manifests;
- selecting a `DocumentEngine`;
- ingestion entry points;
- mapping application results and typed failures for interfaces.

API and CLI must not import ingestion implementations, core models, or contracts directly.

### 3. Make manifest activation mandatory for owned pipeline capabilities

Every optional owned runtime capability must have all four elements:

1. a stable contract;
2. a registered factory or an explicitly documented service-level provider;
3. a versioned manifest field consumed by bootstrap/wiring;
4. wiring and conformance tests.

This applies to redaction, tenant policy, audit, telemetry, review queue, lifecycle ledger,
evaluation, and quality gates. Identity verification remains a service/interface concern rather
than a domain policy: a verifier establishes identity; a tenant policy enforces it.

A declared manifest section that cannot be activated must fail validation. Silent no-ops are
not compatible with manifests as the source of truth.

### 4. Separate executable presets from design blueprints

- `manifests/presets/` contains only configurations that pass load, capability validation, and
  a wiring smoke test.
- Non-executable future examples move to `manifests/blueprints/` and are not represented as
  runnable pipeline manifests.
- Delegated orchestration is selected through `engine.adapter`; it is not described with native
  `planner` or `agents` fields.

### 5. Remove never-functional legacy manifest fields

The active V2 schema will remove `planner`, `agents`, `graph_store`, the legacy `policies` list,
and `modalities` unless a consuming, tested contract exists when the migration is implemented.

These fields do not require a deprecation runtime because they never affected execution and the
package is pre-alpha. Migration documentation and explicit validation errors are still required.

### 6. Enforce the complete dependency model in CI

The layering checker will cover every top-level package:

| Importer | Allowed project imports |
|---|---|
| `core` | `core` |
| `contracts` | `core`, `contracts` |
| domain package | `core`, `contracts`, same domain |
| `adapters` | `core`, `contracts`, `adapters` |
| `orchestration` | `core`, `contracts`, `orchestration` |
| `app` | all non-interface implementation layers: it is the composition root |
| `api` / `cli` | `app`, same interface package |

Current violations will be recorded as an explicit temporary baseline during Step 3, then
removed in Step 4. `--strict` is the final acceptance gate and may not retain exemptions.

---

## Alternatives considered

### Keep `Container` in `app` and introduce a Protocol

This would avoid moving the class, but it leaves the registry — which creates the container —
split across layers and adds an abstraction whose only purpose is compensating for misplaced
ownership. Rejected unless implementation evidence reveals external consumers that make the
move disproportionately expensive.

### Allow orchestration to import app

This matches current code but creates a bidirectional dependency because app already imports
orchestration. It contradicts ADR-0001 and makes process wiring part of engine behavior.
Rejected.

### Forbid the application layer from importing concrete implementations

This looks pure on a diagram but leaves nowhere legitimate to assemble registered domain and
adapter implementations. The present workaround puts those imports in
`orchestration/_default_factories.py`, making orchestration the accidental composition root.
Rejected: `app` is explicitly the outer composition root and may import lower implementation
layers, while `api` and `cli` remain restricted to the application facade.

### Keep direct Python injection as the advanced configuration API

This is useful for tests, but cannot be the only activation path for the product's owned
control-plane differentiators while manifests are advertised as the source of truth. Retain as
a testing/embedding escape hatch, not as the supported deployment path.

### Preserve legacy manifest fields indefinitely

Rejected because accepting ignored fields is more dangerous than a clear pre-alpha breaking
validation error. It creates configurations that appear governed or agentic but execute as a
plain V1 pipeline.

---

## Consequences

### Positive

- Published layering, automated enforcement, and real imports converge.
- A valid manifest becomes an honest description of runtime behavior.
- Owned governance/audit/quality capabilities become engine-independent in practice, not only
  in contracts and tests.
- API and CLI can switch engines and resolve secrets without bespoke wiring.
- Blueprint content cannot be mistaken for deployable configuration.

### Negative / migration cost

- Moving `Container` touches orchestration, bootstrap, tests, and possibly downstream imports.
- Moving `_default_factories.py` changes the documented registration location and requires a
  coordinated update to repository instructions and plugin-development guidance.
- Manifest V2 is a breaking pre-alpha schema change.
- Factories for durable infrastructure require careful secret handling and lifecycle closure.
- API/CLI facade work may expose assumptions currently hidden by concrete `RAGEngine` usage.

### Mitigations

- Characterization tests and the capability matrix are captured before structural changes.
- Move boundaries in one PR before changing manifest behavior.
- Use compatibility re-exports only with a named removal condition.
- Add negative tests proving unsupported manifest fields fail rather than no-op.
- Keep native and LangGraph semantic conformance suites as the engine-parity gate.

---

## Resolved decisions

2. The V2 YAML shape uses typed component selections under `governance`, `observability`,
   `lifecycle`, and `quality`; provider secrets remain references resolved at startup.
3. Identity verification remains service configuration (`TokenVerifier` passed to the API),
   separate from solution-manifest policy enforcement.
5. API and CLI use `load_application()`. Its `ApplicationService` selects the configured
   `DocumentEngine` for answers while retaining native ingestion and retrieval-only use cases.

### Resolved: `app.container` compatibility re-export (Étape 4, 2026-08-07)

Decision #1 is resolved: yes, kept. `src/modular_rag/app/container.py` is now a two-line
re-export (`from modular_rag.orchestration.container import Container`) rather than the real
class definition. No named removal condition has been set yet — it stays until a caller audit
confirms nothing outside `orchestration/`/tests imports `Container` via the old `app.container`
path.

### Resolved: knowledge-graph data model (Étape 8, 2026-08-07)

Decision #4 (whether the native knowledge-graph data model has a justified passive-data role)
is now **resolved: removed**. `memory/graph/knowledge_graph.py` (`KnowledgeGraph`, `GraphNode`,
`GraphEdge`) had zero consumers anywhere outside its own test — no retriever, pipeline, or
manifest-wired component ever constructed one — and `neighbours()`/`subgraph_for_query()` were
genuine multi-hop-traversal logic, not passive storage, so keeping them was never actually
compatible with the "passive data model only" framing this decision asked about. No concrete
need for a passive graph data model was demonstrated. Removed entirely (`git rm -r
src/modular_rag/memory/graph/`), restorable via git history if a real, wired consumer emerges.
`core.enums.GraphRelation` was removed alongside it (orphaned once `GraphEdge` was gone).

---

## Decision record

**Decision:** adopt the ownership, facade, manifest activation, blueprint separation,
legacy-field removal, and CI dependency rules above.

**Status:** Accepted. Herbert Gourout explicitly authorized execution of the full correction
and refactoring plan through completion (2026-08-07), confirmed again after reviewing the
in-progress state of Steps 1-4 and the open items in the capability matrix. This superseded the
draft's earlier placeholder text, which incorrectly left Step 4 gated on a separate acceptance
that had, in fact, already been given in the Decision section above (line 33).
