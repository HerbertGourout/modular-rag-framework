---
paths:
  - "src/modular_rag/orchestration/**/*.py"
description: "Rules for editing orchestration module: registry wiring, engine flow, routing, and state machines."
version: "1.0"
lastUpdated: "2026-06-19"
---

# Règles — édition du module orchestration

> **⚠️ Partially superseded by [ADR-0005](../../docs/adr/0005-document-ai-control-plane-boundary.md)
> (accepted 2026-08-04), added 2026-08-06.** Sections 3 (`QueryRouter`) and 4 (`FlowCompiler`)
> below document components that were removed in Lot 17 (`docs/refactoring-plan.md`) — zero
> test coverage, zero consumers (`RAGEngine` constructed a `QueryRouter` but never called
> `.route()` on it; `FlowCompiler.compile()` had no caller at all). Generic query
> routing/orchestration is delegated to the selected external engine (LangGraph) via the
> `DocumentEngine` port, not built as the native pattern those two sections describe — see
> section 9 below, which already carries this note, and
> `src/modular_rag/orchestration/CLAUDE.md` for the accurate, current file list. Sections 1, 2,
> 5, 6, 7, 8, and 10 remain accurate to current code and are unaffected.

The orchestration layer is responsible for component wiring, execution flow, and state management. This is where the RAG pipeline comes together.

---

## 1. ComponentRegistry Pattern (Wiring Rule)

### Rule: Register All Components Here, Never Wire Elsewhere
Every component (chunker, retriever, generator, guard, adapter) must be registered in `orchestration/registry.py` before use. This is the **single source of truth** for component instantiation.

### Correct Pattern

#### Step 1: Create a Factory Function (registry.py)
```python
from modular_rag.contracts.chunking import Chunker
from modular_rag.ingestion.chunkers import FixedSizeChunker

@_register_factory("FixedSizeChunker", Chunker)
def create_fixed_chunker(config: dict) -> Chunker:
    """
    Instantiate FixedSizeChunker from manifest config.
    
    Args:
        config: {"chunk_size": 512, "overlap": 20}
    """
    return FixedSizeChunker(
        chunk_size=config.get("chunk_size", 512),
        overlap=config.get("overlap", 0)
    )
```

#### Step 2: Select by Name in Manifest YAML
```yaml
# manifests/presets/local-hybrid-rag.yaml
components:
  chunker:
    type: "FixedSizeChunker"
    config:
      chunk_size: 512
      overlap: 20
```

#### Step 3: Instantiate via Registry (not directly)
```python
# ❌ WRONG
from modular_rag.ingestion.chunkers import FixedSizeChunker
chunker = FixedSizeChunker(chunk_size=512)

# ✅ CORRECT
registry = ComponentRegistry()
registry.load_manifest("manifests/presets/local-hybrid-rag.yaml")
chunker = registry.get_component("chunker")
```

### Why This Matters
- **Decoupling**: Swap implementations by changing manifest, not code.
- **Testability**: Mock components via test manifests.
- **Consistency**: All components follow the same wiring pattern.
- **Observability**: Registry can log all instantiations.

---

## 2. RAGEngine.run() Flow & TraceStep Emissions

### Rule: Emit TraceStep at Each Major Stage
The `RAGEngine.run()` method orchestrates the entire pipeline. Each stage must emit a `TraceStep` for observability.

### Correct Flow with TraceStep

```python
from modular_rag.core.models.trace import Trace, TraceStep
import time

def run(self, query: Query) -> Answer:
    """Execute the full RAG pipeline with trace emissions."""
    trace = Trace(query_id=query.id)
    
    # Stage 1: Guard query
    t0 = time.perf_counter()
    is_safe = self._guard.evaluate(query)
    if not is_safe:
        trace.add_step(TraceStep(
            name="guard_query",
            latency_ms=(time.perf_counter() - t0) * 1000,
            metadata={"risk_score": self._guard.risk_score}
        ))
        return Answer(text="Query blocked by safety guard", trace=trace)
    
    trace.add_step(TraceStep(
        name="guard_query",
        latency_ms=(time.perf_counter() - t0) * 1000
    ))
    
    # Stage 2: Retrieve context
    t0 = time.perf_counter()
    context = self._retriever.retrieve(query, trace=trace)
    trace.add_step(TraceStep(
        name="retrieve",
        latency_ms=(time.perf_counter() - t0) * 1000,
        metadata={"chunks": len(context)}
    ))
    
    # Stage 3: Generate answer
    t0 = time.perf_counter()
    answer = self._generator.generate(query, context, trace=trace)
    trace.add_step(TraceStep(
        name="generate",
        latency_ms=(time.perf_counter() - t0) * 1000,
        metadata={"tokens": answer.token_count}
    ))
    
    return answer
```

### TraceStep Fields
- **name** (str): Stage identifier (e.g., "guard_query", "retrieve", "generate")
- **latency_ms** (float): Time taken in milliseconds
- **metadata** (dict): Stage-specific data (chunk count, token count, risk score, etc.)

### Reference
See [src/modular_rag/orchestration/engine.py](src/modular_rag/orchestration/engine.py#L76-L91) for working examples.

---

## 3. QueryRouter: Routing Logic & Fallbacks

### Rule: Router Decides Which Pipeline Path to Use
The `QueryRouter` inspects the query and routes it to the appropriate retrieval/generation strategy.

### Common Routing Decisions
```python
def route(self, query: Query) -> RoutingDecision:
    """Route query to the best pipeline path."""
    
    # Route 1: High-confidence question → Hybrid retrieval
    if self._is_factual_question(query):
        return RoutingDecision(
            strategy="hybrid_retrieval",
            metadata={"confidence": 0.95}
        )
    
    # Route 2: Complex reasoning → Vector retrieval with reranking
    if self._requires_reasoning(query):
        return RoutingDecision(
            strategy="vector_retrieval_with_rerank",
            metadata={"reranker": "ColBERT"}
        )
    
    # Route 3: Unknown → BM25 fallback
    return RoutingDecision(
        strategy="bm25_fallback",
        metadata={"reason": "low_confidence"}
    )
```

### Fallback Pattern
Always provide a fallback for degraded scenarios:
```python
try:
    results = self._retriever.retrieve(query, k=10)
except VectorStoreUnavailableError:
    # Fallback to BM25
    results = self._bm25_retriever.retrieve(query, k=10)
    trace.add_step(TraceStep(
        name="retrieval_fallback",
        metadata={"reason": "vector_store_unavailable"}
    ))
```

---

## 4. FlowCompiler: State Graph Compilation

### Rule: Compile Query Flow to State Graph Before Execution
The `FlowCompiler` converts a logical pipeline definition (manifest YAML) into an executable state machine. This routes to the `DocumentEngine` port (ADR-0005, Lot 7) rather than a native V2 agent-orchestration runtime — must be designed with V1 compatibility.

### Compilation Pattern
```python
def compile_flow(self, manifest: dict) -> StateMachine:
    """Compile manifest into executable state machine."""
    
    states = []
    
    # State 1: Ingest query
    states.append(State(
        name="ingest",
        handler=self._components["chunker"],
        transitions={"success": "retrieve"}
    ))
    
    # State 2: Retrieve context
    states.append(State(
        name="retrieve",
        handler=self._components["retriever"],
        transitions={"success": "generate", "no_results": "fallback"}
    ))
    
    # State 3: Generate answer
    states.append(State(
        name="generate",
        handler=self._components["generator"],
        transitions={"success": "complete", "error": "error_handler"}
    ))
    
    # State 4: Fallback (if no results)
    states.append(State(
        name="fallback",
        handler=self._components["bm25_retriever"],
        transitions={"success": "generate"}
    ))
    
    # State 5: Error handler
    states.append(State(
        name="error_handler",
        handler=self._handle_error,
        transitions={"complete": "complete"}
    ))
    
    return StateMachine(states=states, initial="ingest")
```

---

## 5. StateMachine: State Transitions & Guard Conditions

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

## 6. Dependency Injection in Orchestration

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

## 7. Error Handling in Orchestration

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

## 8. Observability in Orchestration

### Rule: All Orchestration Operations Must Be Traceable
Every component instantiation, route decision, state transition, and fallback must emit TraceStep.

### Trace Emission Checklist
- [ ] Component instantiation logged (via registry)
- [ ] Query route decision logged (via router)
- [ ] Each state transition logged (via state machine)
- [ ] Fallback activations logged (with reason)
- [ ] Errors logged with context (error type, recovery action)
- [ ] Latencies measured (via perf_counter)

### Example
```python
def run(self, query: Query) -> Answer:
    trace = Trace(query_id=query.id)
    
    # Log route decision
    routing = self.router.route(query)
    trace.add_step(TraceStep(
        name="route_decision",
        metadata={"strategy": routing.strategy}
    ))
    
    # Log component selections
    retriever = self.registry.get_component(routing.retriever_key)
    trace.add_step(TraceStep(
        name="component_selection",
        metadata={"retriever": retriever.__class__.__name__}
    ))
    
    # Execute with full trace
    ...
```

---

## 9. V1 vs V2 Scope in Orchestration

### V1 Orchestration (Current)
- ✅ RAGEngine: simple sequential pipeline
- ✅ ComponentRegistry: static component registration
- ✅ QueryRouter: basic routing (factual vs. reasoning)
- ✅ Observability: TraceStep emissions
- ✅ Error handling: fallbacks + logging

### Delegated per ADR-0005 (2026-08-04) — not a native V2 build
- ⚙️ Agent coordination (Coordinator, Planner, Retriever, Synthesizer agents): delegated to the
  selected external engine (Lot 6), routed through `StateMachine`/`FlowCompiler` to the
  `DocumentEngine` port (Lot 7), not built as a native orchestration runtime
- ⚙️ Tool use patterns, multi-turn interactions: same, engine-owned
- ⚙️ Dynamic flow compilation: `FlowCompiler`'s job becomes routing to the external engine, not
  compiling a native agent state graph

### Rule
**Do not implement generic multi-agent orchestration natively.** Leave `StateMachine` and `FlowCompiler` as interfaces until Lot 7 defines the `DocumentEngine` port they route to. Focus on `RAGEngine` and `ComponentRegistry` for V1 completion in the meantime.

---

## 10. Testing Orchestration

### Unit Tests (tests/unit/orchestration/)
```python
# Test registry factory pattern
def test_registry_creates_components():
    registry = ComponentRegistry()
    registry.load_manifest({"chunker": {"type": "FixedSizeChunker", "config": {...}}})
    chunker = registry.get_component("chunker")
    assert isinstance(chunker, Chunker)

# Test router logic
def test_router_selects_correct_strategy():
    router = QueryRouter()
    decision = router.route(Query(text="What is RAG?"))
    assert decision.strategy == "hybrid_retrieval"

# Test engine flow
def test_engine_emits_trace_steps():
    engine = RAGEngine(guard, retriever, generator)
    answer = engine.run(query)
    assert len(answer.trace.steps) >= 3  # guard, retrieve, generate
```

### Integration Tests (tests/integration/)
Require Qdrant on localhost:6333. Test full pipeline end-to-end.

```python
@pytest.mark.integration
def test_full_rag_pipeline():
    engine = RAGEngine(
        guard=PromptGuard(),
        retriever=VectorRetriever(store=QdrantStore(...)),
        generator=OpenAIGenerator(...)
    )
    answer = engine.run(Query(text="What is RAG?"))
    assert answer.text
    assert len(answer.trace.steps) > 0
```

---

## Summary: Orchestration Dos & Don'ts

### ✅ DO
- Register all components in `orchestration/registry.py`
- Select components by name in manifest YAML
- Emit `TraceStep` at each major stage
- Inject dependencies via constructor
- Handle errors with fallbacks
- Use `ComponentRegistry.wire()` for dependency resolution
- Test routing logic in unit scope
- Test full pipeline in integration scope

### ❌ NEVER
- Instantiate components directly (use registry)
- Hardcode component selections in Python
- Omit TraceStep emissions
- Use global singletons for components
- Silence errors without logging
- Implement V2 agent features in V1
- Mix concerns (orchestration + domain logic)
- Create new top-level orchestration files without an ADR

---

## Questions Before Editing Orchestration

Before modifying this module, ask yourself:
1. **Is this V1 or V2 scope?** (V1: RAGEngine, Registry. V2: Agent orchestration.)
2. **Does this require a Registry entry?** (If so, add the factory first.)
3. **Should this emit TraceStep?** (If user-visible, yes.)
4. **What tests are needed?** (Unit for logic, integration for full pipeline.)
5. **Does this violate layering?** (Orchestration imports domain modules only via contracts.)

---

Good luck editing orchestration!
