# CLAUDE.md — Orchestration Module

This file provides guidance for Claude working on the orchestration (registry, engine, wiring) layer. Read this **before editing any file in this directory**.

Rewritten in full 2026-08-06 (documentation audit, `docs/documentation-audit-2026-08.md`): the
previous version documented `router.py`/`QueryRouter`, `compiler.py`, and `config.py` in detail
with invented APIs (`RouterDecision`, `RAGConfig`, `QueryRequest`/`QueryResponse`) that never
matched this module's real code. `QueryRouter` and `FlowCompiler` did exist once but were
removed in Lot 17 (`docs/refactoring-plan.md`) — zero consumers, zero test coverage,
superseded by [ADR-0005](../../../docs/adr/0005-document-ai-control-plane-boundary.md) §5.2
(generic query routing/orchestration is delegated to the selected external engine, not built
natively). `compiler.py`/`config.py` never existed under this directory at all. This version
describes only the files actually present here today.

---

## Real files in this directory

```
orchestration/
├── __init__.py
├── registry.py            ComponentRegistry — role/type-name -> factory, wire(manifest) -> Container
├── engine.py               RAGEngine — the V1 sequential pipeline (ingest, answer, retrieve, delete, rebuild, erase)
├── native_engine.py        NativeEngineAdapter — wraps RAGEngine behind the DocumentEngine port (Lot 8)
├── state_machine.py        PipelineState / PipelineStateMachine — tracks transitions during one run
├── reconciliation.py       IndexReconciler — detects/repairs ledger-vs-index divergence (Lot 12b)
└── _default_factories.py   register_defaults(registry) — registers every built-in component type
```

`adapters/llms/langgraph_engine.py`'s `LangGraphEngineAdapter` (the second `DocumentEngine`
implementation, Lot 15) is **not** in this directory — it lives in `adapters/` because it must
not depend on `app.container.Container` directly (adapters/ layering rule); it depends on a
local structural Protocol instead. Both `NativeEngineAdapter` and `LangGraphEngineAdapter`
route through the same `Container` this module wires.

**Changes here affect every retrieval, generation, and engine-adapter call.**

---

## Rule 1: Registry Pattern — Manifest-Driven Wiring

### NEVER Wire Components in Python

### ❌ FORBIDDEN

```python
# ❌ Direct Python instantiation (breaks manifest-driven architecture)
from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker
from modular_rag.retrieval.retrievers.bm25 import BM25Retriever

chunker = FixedSizeChunker(chunk_size=512)
retriever = BM25Retriever()
```

### ✅ ALLOWED

```python
# ✅ Manifest-driven via registry (this is what app/bootstrap.py's
# load_pipeline() actually does)
from modular_rag.app.bootstrap import load_manifest
from modular_rag.orchestration.registry import ComponentRegistry

manifest = load_manifest("manifests/presets/local-hybrid-rag.yaml")
registry = ComponentRegistry.default()   # pre-loaded with every built-in factory
container = registry.wire(manifest)      # -> Container holding every wired component

chunker = container.chunker
retriever = container.retriever
```

### Why This Matters

- **Manifest-driven**: All configuration lives in YAML, not scattered in Python code
- **Lazy loading**: Heavy adapter dependencies (qdrant-client, sentence-transformers, openai,
  anthropic, fitz) import only inside the method that uses them
- **Testability**: Easy to swap implementations for testing
- **Extensibility**: New components added without modifying existing Python code

---

## Rule 2: ComponentRegistry — Real Interface

```python
class ComponentRegistry:
    """Map component type names -> factory functions, then wire a manifest into a Container."""

    def register(self, role: str, type_name: str, factory: Callable[[ComponentConfig], Any]) -> None: ...
    def available_types(self, role: str) -> frozenset[str]: ...
    def wire(self, manifest: PipelineManifest) -> Container: ...

    @classmethod
    def default(cls) -> ComponentRegistry:
        """Registry pre-loaded with every built-in adapter (via _default_factories.register_defaults)."""
```

Roles pre-declared in `__init__`: `chunker`, `embedder`, `indexer`, `retriever`, `reranker`,
`generator`, `guard`, `evaluator`, plus two forward-looking, currently-empty role slots:
`planner` and `graph_store` — reserved for the delegated-engine adapter targets
(`adapters/graphstores/`, per ADR-0005/CLAUDE.md's Adapter Stubs table), not dead code; `wire()`
does not read `manifest.planner`/`manifest.graph_store` yet, so registering a factory under
either role has no effect until that wiring is added.

### Registering Components

**Location**: `orchestration/_default_factories.py` — the single source of truth for every
built-in factory. Real pattern:

```python
def register_defaults(reg: ComponentRegistry) -> None:
    reg.register("chunker", "fixed", lambda cfg: FixedSizeChunker(**cfg.config))
    reg.register("retriever", "hybrid", lambda cfg: HybridRetriever(**cfg.config))
    # ... one register() call per (role, type_name) pair
```

### Never Register Here

- ❌ Do NOT register in domain modules (`ingestion/`, `retrieval/`, etc.)
- ❌ Do NOT register in `adapters/` (they only implement Protocols; wiring stays here)
- ✅ Register ONLY in `_default_factories.py`

---

## Rule 3: RAGEngine — Real Pipeline Execution

```python
class RAGEngine:
    """Main entry point: ingest documents and answer queries via a configured pipeline."""

    def __init__(self, container: Container) -> None: ...

    # Public accessors (Lot 8 — so API/CLI never reach into a private container)
    @property
    def manifest_id(self) -> str: ...
    @property
    def chunker(self) -> Chunker: ...
    @property
    def retriever(self) -> Retriever: ...

    def ingest(self, documents: list[Document]) -> int: ...
    def ingest_chunks(self, chunks: list[Chunk]) -> int: ...
    def answer(self, question: str, **query_kwargs: object) -> Answer: ...
    def retrieve(self, question: str, k: int = 10, tenant_id: str | None = None) -> list[RetrievedChunk]: ...
    def delete_document(self, document_key: str) -> None: ...
    def rebuild_document(self, ...) -> None: ...
    def erase_document(self, document_key: str) -> ErasureProof: ...
```

`answer()`'s actual fixed pipeline (`_run_steps`, `engine.py`), in order, each step gated on
whether the matching optional component is configured on the `Container`:

1. Tenant-isolation identity check (`Container.tenant_policy.enforce_query()`, fail-closed, Lot 11b)
2. Query guard (`Container.guard.check_query()`)
3. Retrieval (`Container.retriever.retrieve()`)
4. Tenant chunk filtering (`Container.tenant_policy.filter_chunks()`)
5. Reranking (`Container.reranker.rerank()`, if configured)
6. Generation (`Container.generator.generate()`)
7. Answer guard (`Container.guard.check_answer()`)
8. Redaction (`Container.redactor.redact()`, if configured)
9. Human-review flagging (`Container.review_queue`, if configured)

There is no dynamic routing between strategies — every request runs this same sequence. Query
classification/strategy selection was `QueryRouter`'s job; it was removed in Lot 17 because
nothing ever called `.route()` on it (see the file header).

### TraceStep Emissions (MANDATORY)

Real pattern — see `engine.py`'s actual `_run_steps`/`_retrieve` for the working example:

```python
from modular_rag.core.models.trace import Trace, TraceStep
import time

t0 = time.perf_counter()
context = self._retrieve(query, k=k)
trace.add_step(TraceStep(name="retrieve", metadata={"chunks": len(context)}))
```

`TraceStep` fields: `name: str`, `latency_ms: float = 0.0`, `metadata: dict[str, Any]`. Every
generator also emits its own step (e.g. `"openai_generate"`) inside its own `generate()` — do
not add a second wrapping step around a call that already instruments itself (Lot 10 fixed
exactly this double-counting bug once).

### When to Emit TraceStep

- ✅ Guard evaluation (query and answer)
- ✅ Retrieval (chunk count)
- ✅ Reranking (if configured)
- ✅ Generation (model used, tokens, latency — inside the generator itself)
- ✅ Tenant filtering (chunks before/after)
- ❌ NEVER: full query text if it may contain PII — use `Container.redactor` first
- ❌ NEVER: full answer text if it may contain secrets

---

## Rule 4: PipelineStateMachine

```python
class PipelineState(StrEnum):
    IDLE = "idle"
    GUARDING_QUERY = "guarding_query"
    RETRIEVING = "retrieving"
    RERANKING = "reranking"
    GENERATING = "generating"
    GUARDING_ANSWER = "guarding_answer"
    EVALUATING = "evaluating"
    DONE = "done"
    ERROR = "error"
```

`PipelineStateMachine` (`state_machine.py`) enforces a fixed transition matrix between these
states and is used on **every** `RAGEngine.answer()` call today — this is real, current V1
machinery, not a V2+ stub. `transition(to)` raises if the target state isn't reachable from the
current one.

---

## Rule 5: DocumentEngine adapters route through this module's wiring

`NativeEngineAdapter` (`native_engine.py`, Lot 8) wraps a `RAGEngine` instance behind the
vendor-neutral `DocumentEngine` port (`contracts/engine.py`, Lot 7) — an empty, honest
capability set (no streaming/cancellation/governance-hook support). `LangGraphEngineAdapter`
(`adapters/llms/langgraph_engine.py`, Lot 15) is the second implementation, running the same
wired `Container` components through a real LangGraph `StateGraph` instead — it declares
`STREAMING`/`GOVERNANCE_INTERCEPT`/`CANCELLATION`. `app/bootstrap.py`'s `load_engine()` selects
between them from a manifest's `engine.adapter` field (`"native"` default, or `"langgraph"`).
Both must pass the same governance/tenant-isolation tests — see
`docs/refactoring/lot-15-langgraph-adapter.md` and `lot-18-pilot-and-closure.md` for two real
parity bugs found and fixed between them.

---

## Rule 6: IndexReconciler

`reconciliation.py`'s `IndexReconciler` (Lot 12b) detects and repairs divergence between a
`LifecycleLedger`'s expected chunk ids and what the indexer/retriever actually hold —
`check()`/`repair()`, orphan-deletion only, never fabricates missing content. Unrelated to
query-time routing; this runs as an operational/maintenance task, not part of `answer()`.

---

## Checklist Before Editing

- [ ] Am I adding a new component type? Register it in `_default_factories.py`, select it by
      name in a manifest — never instantiate directly.
- [ ] Am I changing `RAGEngine`'s flow? Emit a `TraceStep` for the new step; update
      `PipelineStateMachine`'s transition matrix if it adds/removes a state.
- [ ] Am I touching `LangGraphEngineAdapter`? Any governance/tenant-isolation change here needs
      the identical change there too (Lot 15/18's own parity-bug history is the reason this
      rule exists).
- [ ] Does this change wire components in Python? (❌ NO — use the manifest + registry)
- [ ] Does this expose secrets or raw PII in a `TraceStep`'s metadata? (❌ NO)

---

## References

- [ADR-0005: Document-AI Control Plane Boundary](../../../docs/adr/0005-document-ai-control-plane-boundary.md) — why generic routing/orchestration is delegated, not native
- [contracts/engine.py's compatibility policy](../../../docs/architecture/document-engine-contract.md)
- [.claude/rules/orchestration.md](../../../.claude/rules/orchestration.md) — broader orchestration-layer rules
- [docs/refactoring/lot-17-prototype-retirement.md](../../../docs/refactoring/lot-17-prototype-retirement.md) — why `router.py`/`flow_compiler.py` were removed
- [CONTRIBUTING.md](../../../CONTRIBUTING.md) — component addition workflow
