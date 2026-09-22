---
paths:
  - "src/modular_rag/agents/**/*.py"
description: "Rules for implementing agents/: the DocumentEngine adapter-integration target, not a native agent runtime."
version: "2.0"
lastUpdated: "2026-08-06"
---

# Rules — editing the agents module

*(Heading translated to English 2026-09-22, matching `contracts.md`, `security.md` and
`tests.md`; the body was already English.)*

Per [ADR-0005](../../docs/adr/0005-document-ai-control-plane-boundary.md) §5.2 (accepted
2026-08-04), generic multi-agent orchestration is **delegated** to a selected external engine
(LangGraph, [ADR-0006](../../docs/adr/0006-external-engine-selection.md)) via the
`DocumentEngine` port (`contracts/engine.py`) — this module is not a native agent runtime and
never will be. Its job is to host whatever adapter-integration glue code calling into that
engine eventually needs, alongside `adapters/llms/langgraph_engine.py` (the real, current
`LangGraphEngineAdapter` implementation).

[Lot 17](../../docs/refactoring/lot-17-prototype-retirement.md) removed the five pre-ADR-0005
native agent prototypes that used to live here (`CoordinatorAgent`, `ExtractorAgent`,
`RetrieverAgent`, `SynthesizerAgent`, `ValidatorAgent`) — zero test coverage, zero consumers,
and they implemented exactly the capability ADR-0005 now delegates. `agents/` today is five
empty placeholder directories (`coordinator/`, `extractor/`, `retriever/`, `synthesizer/`,
`validator/`, each holding only a `.gitkeep`) plus `__init__.py`'s docstring explaining this.

---

## 1. What Belongs Here (and What Doesn't)

### Rule: This Directory Hosts Adapter-Integration Code, Not Agent Logic
There is no `contracts/agents.py` — it was deleted in Lot 17 along with the prototypes it
described. Any agent *behavior* (planning, tool use, multi-step reasoning) belongs in the
selected external engine, reached through `contracts/engine.py`'s `DocumentEngine` Protocol:
```python
def run(self, request: EngineRequest, context: ExecutionContext) -> EngineResult: ...
def astream(self, request: EngineRequest, context: ExecutionContext) -> AsyncIterator[EngineStep]: ...
@property
def capabilities(self) -> frozenset[EngineCapability]: ...
```
(see `contracts/engine.py` for the full, real Protocol). `agents/` may host code that:
- Adapts `DocumentEngine` events into this framework's own `Trace`/`Answer` shapes
- Bridges engine-native tool definitions to this project's registry-wired components
- Anything else that's integration glue, not orchestration logic itself

**Do NOT** define a new native coordination Protocol here. If a design decision would
reintroduce `CoordinatorAgent`-shaped orchestration, it needs a new ADR, not a quiet addition
to this module.

---

## 2. State and Context Flow

State passing across a multi-step agent workflow (context accumulation across planning,
retrieval, generation, validation steps) is the delegated engine's concern, not this module's —
`DocumentEngine.astream()` yields `EngineStep`s while engine-private state remains inside the adapter
needs internally.

`RAGEngine.answer(question: str) -> Answer` (`orchestration/engine.py`) remains the real,
current V1 path for the native (non-delegated) sequential pipeline — it builds a `Query` and
runs guard→retrieve→rerank→generate internally via `_run()`, with no per-step agent handoff.

Any adapter-integration code in `agents/` that needs to track state across an engine's streamed
events should do so locally, scoped to the adapter call — not by inventing a new shared
cross-agent context type.

---

## 3. Observability: TraceStep / EngineStep

### Rule: Every Adapter-Integration Call Must Be Traceable
This is non-negotiable, matching every other layer of this codebase (see
[.claude/.instructions.md](../.instructions.md) §3). `contracts/engine.py`'s `EngineStep` is
deliberately shape-compatible with `core/models/trace.py`'s `TraceStep`
(`name`/`latency_ms`/`metadata`) so the two can be folded together —
`LangGraphEngineAdapter._node_generate()` (`adapters/llms/langgraph_engine.py`) is the real,
current example: it runs the generator against a local `Trace`, then converts each
`trace.steps` entry into an `EngineStep` and appends it to the graph state's step list. Any new
`agents/` glue code should follow the same fold-not-duplicate pattern rather than inventing a
separate tracing mechanism.

---

## 4. Wire via `app/bootstrap.py`, Not the Component Registry

### Rule: Engine Selection Goes Through `load_engine()`
`DocumentEngine` isn't a multi-instance component type like a retriever or generator — a
pipeline selects exactly one engine, so it isn't wired via `ComponentRegistry.register()`/manifest
`components:` blocks the way chunkers/retrievers/generators are. The real, current selection
path is `app/bootstrap.py::load_engine(path)`: it reads the manifest's `engine.adapter` field
(`"native"` → `NativeEngineAdapter`, `"langgraph"` → `LangGraphEngineAdapter`, anything else →
`ConfigurationError`) and returns the constructed adapter, still wrapping the same
`ComponentRegistry.wire()`-built `Container` both adapters share for chunker/retriever/guard/
generator selection. Any new `agents/` glue code should be reached through this same function,
not instantiated directly in application code.

---

## 5. Error Handling

### Rule: Use the Existing Error Hierarchy
`core/errors.py` defines the engine-boundary errors — do not invent an `AgentError`:
```python
EngineError               # Base error for all DocumentEngine failures (ADR-0005 §5.2 / ADR-0006)
EngineTimeoutError         # A DocumentEngine call exceeded its deadline
EngineCancelledError       # Cancelled via the ExecutionContext's CancellationToken
EngineCapabilityError      # Caller invoked a method the adapter doesn't declare support for
```
Translate engine lifecycle/capability failures when one of these types applies, while preserving
the framework's existing `SecurityError`/`PolicyViolationError`. The current LangGraph adapter
also lets a generator exception propagate; do not document or rely on a blanket translation rule
that the implementation does not provide.

---

## 6. Testing

### Rule: Test Against the Real `DocumentEngine` Conformance Suite
There is no `tests/contract/test_agents_conformance.py` — `contracts/agents.py` was deleted in
Lot 17 along with the tests for it. The real, current conformance tests for this boundary are in
[`tests/contract/test_engine_conformance.py`](../../tests/contract/test_engine_conformance.py),
which test `DocumentEngine` implementations (including `FakeDocumentEngine`,
`tests/contract/fakes/document_engine.py`) against the real Protocol. Add new cases there for
any new `DocumentEngine` behavior; don't create a parallel test file for `agents/`.

`tests/unit/adapters/llms/test_langgraph_engine.py` is the real unit-test reference for how the
`LangGraphEngineAdapter` implementation itself is tested.

---

## 7. Summary

### Current scope (post-Lot 17, per ADR-0005 §5.2)
- ✅ `agents/` hosts adapter-integration glue calling into the selected external engine via
  `DocumentEngine` — currently five empty placeholder directories, nothing implemented yet
- ✅ Engine selection goes through `app/bootstrap.py::load_engine()`, not the component registry
- ✅ Any code here must use the existing error hierarchy where applicable and fold its own tracing
  into `EngineStep`/`TraceStep`
- ✅ Tests belong in `tests/contract/test_engine_conformance.py` (Protocol conformance) and
  alongside `tests/unit/adapters/llms/test_langgraph_engine.py` (adapter-specific behavior)

### Out of scope — do not build here
- ❌ A native multi-agent coordination Protocol or runtime (delegated per ADR-0005 §5.2)
- ❌ A new cross-agent shared-context/state-passing mechanism (the engine owns this internally)
- ❌ Registering `agents/` components via `ComponentRegistry`/manifest `components:` blocks

---

## 8. Questions Before Editing Agents

Before modifying this module, ask yourself:
1. **Is this adapter-integration glue, or orchestration logic?** Glue belongs here; logic
   belongs to the selected external engine.
2. **Does this reintroduce native coordination?** If a change would let this framework decide
   *how* agents reason/plan (not just adapt engine output), it needs a new ADR first.
3. **Am I using the real `DocumentEngine` Protocol** (`contracts/engine.py`), not inventing a
   new one?
4. **Have I added a case to `tests/contract/test_engine_conformance.py`** if the change touches
   `DocumentEngine` behavior?

---

Good luck working with agents!
