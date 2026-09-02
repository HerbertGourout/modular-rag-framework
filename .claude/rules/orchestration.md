---
paths:
  - "src/modular_rag/orchestration/**/*.py"
description: "Rules for editing orchestration module: registry wiring, engine flow, and state machines. Routing/flow compilation are delegated per ADR-0005."
version: "2.1"
lastUpdated: "2026-08-07"
---

# Règles — édition du module orchestration

The orchestration layer is responsible for component wiring, execution flow, and state management. This is where the RAG pipeline comes together.

Per [ADR-0005](../../docs/adr/0005-document-ai-control-plane-boundary.md) §5.2, query routing and flow compilation are delegated to a selected external engine (§3 below) — this file no longer documents a native design for either.

---

## 1. ComponentRegistry Pattern (Wiring Rule)

> **Corrected 2026-08-07 (Étape 11):** this section previously showed a fictional
> `@_register_factory` decorator, a `registry.load_manifest()`/`registry.get_component()` API,
> and a manifest shape (`components: chunker: type: ...`) that never matched the real, flat
> top-level manifest fields (`chunker:`, `retriever:`, etc.). Rewritten against the real
> `ComponentRegistry` API (`orchestration/registry.py`) and registration location
> (`app/default_factories.py`, moved from `app/default_factories.py` in Étape 4).

### Rule: Register All Components in `app/default_factories.py`, Never Wire Elsewhere
Every component (chunker, retriever, generator, guard, adapter) must be registered there before
use. This is the **single source of truth** for component instantiation.

### Correct Pattern

#### Step 1: Register a Factory (`app/default_factories.py`, inside `register_defaults()`)
```python
from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker

def register_defaults(reg: ComponentRegistry) -> None:
    ...
    reg.register("chunker", "fixed", lambda cfg: FixedSizeChunker(**cfg.config))
```

#### Step 2: Select by Name in Manifest YAML
```yaml
# manifests/presets/local-hybrid-rag.yaml — top-level fields, no components: wrapper
chunker:
  type: "fixed"
  config:
    chunk_size: 512
    chunk_overlap: 64
```

#### Step 3: Instantiate via `wire()` (not directly)
```python
# ❌ WRONG
from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker
chunker = FixedSizeChunker(chunk_size=512)

# ✅ CORRECT
from modular_rag.app.bootstrap import load_pipeline
engine = load_pipeline("manifests/presets/local-hybrid-rag.yaml")  # -> RAGEngine
chunker = engine.chunker
```

### Why This Matters
- **Decoupling**: Swap implementations by changing manifest, not code.
- **Testability**: Mock components via test manifests.
- **Consistency**: All components follow the same wiring pattern.
- **Observability**: Registry logs every registration (`registry.registered` structlog events).

---

## 2. RAGEngine.answer() Flow & TraceStep Emissions

> **Corrected 2026-08-07 (Étape 11):** the example below previously showed a `run(query: Query)`
> method, a boolean-returning guard (`self._guard.evaluate(query) -> bool`), and
> `retriever.retrieve(query, trace=trace)`/`generator.generate(query, context, trace=trace)`
> keyword-argument calls — none of which match the real signatures. `SecurityGuard.check_query()`
> returns a `GuardResult` (`allowed`/`reason`/`risk_score`), `Retriever.retrieve()` takes no
> `trace` argument at all (retrieval isn't separately traced by the retriever itself), and
> `Generator.generate(query, context, trace)` takes `trace` positionally, not as a keyword.

### Rule: Emit TraceStep at Each Major Stage
The real method is `RAGEngine.answer(question: str, **query_kwargs) -> Answer`
(`orchestration/engine.py`), which delegates to a private `_run_steps()`. Each stage is gated on
whether its optional component is configured on the `Container`; see
`src/modular_rag/orchestration/CLAUDE.md` for the full 9-step list. Simplified illustration of
the pattern (real code, not the full method):

```python
from modular_rag.core.models.trace import Trace, TraceStep
import time

def answer(self, question: str, **query_kwargs: object) -> Answer:
    query = Query(text=question, **query_kwargs)
    trace = Trace(query_id=query.id)

    if self._c.guard is not None:
        result = self._c.guard.check_query(query)
        if not result.allowed:
            raise SecurityError(result.reason or "Query blocked by safety guard.")

    t0 = time.perf_counter()
    context = self._c.retriever.retrieve(query)
    trace.add_step(TraceStep(
        name="retrieve",
        latency_ms=(time.perf_counter() - t0) * 1000,
        metadata={"chunks": len(context)},
    ))

    # generate() takes `trace` positionally and emits its own TraceStep internally —
    # do not wrap it in a second "generate" step (Lot 10 fixed exactly this double-count).
    answer = self._c.generator.generate(query, context, trace)
    return answer
```

### TraceStep Fields
Real fields (`core/models/trace.py`): `name: str`, `input_tokens: int = 0`,
`output_tokens: int = 0`, `latency_ms: float = 0.0`, `metadata: dict[str, Any]`.

### Reference
See `orchestration/engine.py`'s real `_run_steps()`/`answer()` for the actual, complete
9-step flow — this section is illustrative, not a copy of the real method body.

---

## 3. Query Routing and Flow Compilation — Delegated

> **Delegated per [ADR-0005](../../docs/adr/0005-document-ai-control-plane-boundary.md) §5.2.**
> Query routing and flow compilation are delegated to a selected external engine via the
> `DocumentEngine` port, not built natively in this repository. The prototype implementations
> (`orchestration/router.py`'s `QueryRouter`, `orchestration/flow_compiler.py`'s `FlowCompiler`)
> were removed in [Lot 17](../../docs/refactoring/lot-17-prototype-retirement.md) — zero test
> coverage, zero consumers (`RAGEngine` constructed a `QueryRouter` but never called `.route()`
> on it; `FlowCompiler.compile()` had no caller at all).
>
> The real, current routing mechanism is `app/bootstrap.py::load_engine()`: it reads a
> manifest's `engine.adapter` field and returns either `NativeEngineAdapter` (V1's fixed
> guard→retrieve→rerank→generate sequence) or `LangGraphEngineAdapter`
> (`adapters/llms/langgraph_engine.py`) — see
> [`orchestration/CLAUDE.md`](../../src/modular_rag/orchestration/CLAUDE.md) for the accurate,
> current file list.

---

## 4. StateMachine: State Transitions & Guard Conditions

### Rule: Define Clear State Transitions with Guards
State transitions must be deterministic. Use guard conditions to branch on outcomes.

### Correct Pattern
```python
class StateMachine:
    def __init__(self, states: list[State], initial: str):
        self.states = {s.name: s for s in states}
        self.current_state = self.states[initial]
    
    def transition(self, outcome: str) -> State:
        """Move to next state based on outcome."""
        next_state_name = self.current_state.transitions.get(outcome)
        
        if not next_state_name:
            raise InvalidTransitionError(
                f"No transition from {self.current_state.name} "
                f"on outcome '{outcome}'"
            )
        
        self.current_state = self.states[next_state_name]
        return self.current_state
    
    def execute(self, input_data: dict) -> dict:
        """Execute state machine to completion."""
        current_input = input_data
        
        while not self._is_terminal_state(self.current_state.name):
            # Execute current state handler
            output = self.current_state.handler(current_input)
            
            # Emit trace step
            trace.add_step(TraceStep(
                name=self.current_state.name,
                metadata={"output_type": type(output).__name__}
            ))
            
            # Determine outcome (success, failure, no_results, etc.)
            outcome = self._determine_outcome(output)
            
            # Transition to next state
            self.transition(outcome)
            current_input = output
        
        return current_input
    
    def _is_terminal_state(self, state_name: str) -> bool:
        """Check if state is terminal (no outgoing transitions)."""
        return not self.states[state_name].transitions
```

### Guard Conditions Example
```python
# Guard: only proceed if retrieval returned results
def transition(self, outcome: str) -> State:
    if outcome == "no_results" and not self._has_fallback():
        raise PipelineError("No results and no fallback available")
    return super().transition(outcome)
```

---

## 5. Dependency Injection in Orchestration

### Rule: Inject Dependencies via Constructor, Not Globals
Orchestration components must receive dependencies through their constructor for testability.

### Correct Pattern
```python
class RAGEngine:
    def __init__(
        self,
        guard: SecurityGuard,
        retriever: Retriever,
        generator: Generator,
        trace: Trace = None
    ):
        self.guard = guard
        self.retriever = retriever
        self.generator = generator
        self.trace = trace or Trace()
```

### ❌ Avoid
```python
# Global singletons (hard to test)
_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = RAGEngine(...)
    return _engine
```

---

## 6. Error Handling in Orchestration

### Rule: Catch Component-Level Errors, Never Silence Them
Orchestration must handle errors gracefully but log all failures.

### Correct Pattern
```python
def run(self, query: Query) -> Answer:
    trace = Trace()
    
    try:
        # Guard phase
        try:
            is_safe = self.guard.evaluate(query)
        except GuardEvaluationError as e:
            trace.add_step(TraceStep(
                name="guard_error",
                metadata={"error": str(e)}
            ))
            return Answer(
                text="Security guard evaluation failed",
                is_safe=False,
                trace=trace
            )
        
        # Retrieval phase with fallback
        try:
            context = self.retriever.retrieve(query)
        except RetrievalError as e:
            trace.add_step(TraceStep(
                name="retrieval_error",
                metadata={"fallback": "bm25"}
            ))
            context = self.bm25_retriever.retrieve(query)
        
        # Generation phase
        answer = self.generator.generate(query, context)
        return answer
    
    except Exception as e:
        # Log and re-raise
        logger.error(f"Pipeline error: {e}", exc_info=True)
        raise
```

---

## 7. Observability in Orchestration

### Rule: All Orchestration Operations Must Be Traceable
Every component instantiation, engine call, state transition, and fallback must emit TraceStep.

### Trace Emission Checklist
- [ ] Component instantiation logged (via registry)
- [ ] Engine selection logged (`NativeEngineAdapter` vs `LangGraphEngineAdapter`)
- [ ] Each state transition logged (via state machine)
- [ ] Fallback activations logged (with reason)
- [ ] Errors logged with context (error type, recovery action)
- [ ] Latencies measured (via perf_counter)

### Example
```python
def answer(self, question: str) -> Answer:
    trace = Trace(query_id=query.id)

    # Log component selections
    retriever = self.registry.get_component("retriever")
    trace.add_step(TraceStep(
        name="component_selection",
        metadata={"retriever": retriever.__class__.__name__}
    ))

    # Execute with full trace
    ...
```

---

## 8. Native vs. Delegated Scope in Orchestration

### Native (current)
- ✅ `RAGEngine`: fixed guard→retrieve→rerank→generate sequential pipeline
- ✅ `ComponentRegistry`: static component registration
- ✅ Observability: TraceStep emissions
- ✅ Error handling: fallbacks + logging

### Delegated per ADR-0005 §5.2 — not a native build
- ⚙️ Query routing and flow compilation: delegated to the selected external engine
  (LangGraph) via the `DocumentEngine` port — see §3 above
- ⚙️ Multi-agent coordination (planner/retriever/extractor/synthesizer/validator): same,
  engine-owned; see `src/modular_rag/agents/`
- ⚙️ Tool use patterns, multi-turn interactions: same, engine-owned

### Rule
**Do not implement generic query routing or multi-agent orchestration natively.** Route through
`app/bootstrap.py::load_engine()` and the `DocumentEngine` port instead.

---

## 9. Testing Orchestration

### Unit Tests (tests/unit/orchestration/)
```python
# Test registry factory pattern
def test_registry_creates_components():
    registry = create_default_registry()
    container = registry.wire(manifest)
    assert container.retriever is not None

# Test engine flow
def test_engine_emits_trace_steps():
    engine = RAGEngine(container)
    answer = engine.answer("What is RAG?")
    assert answer.trace_id is not None
```

### Integration Tests (tests/integration/)
Require Qdrant on localhost:6333. Test full pipeline end-to-end.

```python
@pytest.mark.integration
def test_full_rag_pipeline():
    registry = create_default_registry()
    container = registry.wire(manifest)  # manifest selects real Qdrant + OpenAI adapters
    engine = RAGEngine(container)
    answer = engine.answer("What is RAG?")
    assert answer.text
    assert answer.trace_id is not None
```

---

## Summary: Orchestration Dos & Don'ts

### ✅ DO
- Register all components in `app/default_factories.py` (moved from `app/default_factories.py` in Étape 4 — `orchestration/` may only import core/contracts/orchestration)
- Select components by name in manifest YAML
- Emit `TraceStep` at each major stage
- Inject dependencies via `Container`, built by `ComponentRegistry.wire()`
- Handle errors with fallbacks
- Route engine selection through `app/bootstrap.py::load_engine()`
- Test engine/pipeline logic in unit scope
- Test full pipeline in integration scope

### ❌ NEVER
- Instantiate components directly (use registry)
- Hardcode component selections in Python
- Omit TraceStep emissions
- Use global singletons for components
- Silence errors without logging
- Implement native query routing or multi-agent orchestration (delegated per ADR-0005)
- Mix concerns (orchestration + domain logic)
- Create new top-level orchestration files without an ADR

---

## Questions Before Editing Orchestration

Before modifying this module, ask yourself:
1. **Is this native orchestration or delegated-engine scope?** (Native: `RAGEngine`,
   `ComponentRegistry`, `StateMachine`. Delegated: routing, multi-agent coordination — goes
   through `DocumentEngine`.)
2. **Does this require a registry entry?** (If so, add the factory in `app/default_factories.py`.)
3. **Should this emit TraceStep?** (If user-visible, yes.)
4. **What tests are needed?** (Unit for logic, integration for full pipeline.)
5. **Does this violate layering?** (Orchestration imports domain modules only via contracts.)

---

Good luck editing orchestration!
