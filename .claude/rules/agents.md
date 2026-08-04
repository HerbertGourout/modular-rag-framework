---
paths:
  - "src/modular_rag/agents/**/*.py"
description: "Rules for implementing agents: interfaces, state passing, TraceStep emissions, and orchestration patterns."
version: "1.0"
lastUpdated: "2026-06-19"
---

# Règles — édition du module agents

> **⚠️ Superseded in part by [ADR-0005](../../docs/adr/0005-document-ai-control-plane-boundary.md)
> (accepted 2026-08-04).** The "V2+ expands to full agent coordination" line below describes a
> native `Coordinator`/`HierarchicalCoordinator` build that is now **delegated** to a selected
> external engine instead. The V1 interface patterns in this file remain valid; the V2+
> native-coordination sections are historical design reference only, not an implementation
> target. Full retirement/rewrite is Lot 17 scope in `docs/refactoring-plan.md`.

The agents module defines the interfaces and base patterns for agentic orchestration. In V1, this is **minimal scope** (interfaces only). V2+ expands to full agent coordination.

---

## 1. Agent Interfaces (V1 Scope)

### Rule: Define All Agent Types as Protocols in `contracts/agents.py`
V1 agents are defined as Protocols (interfaces), not implementations. This allows flexible composition in V2+ without constraining the design now.

### Core Agent Types (V1)
```python
# contracts/agents.py (Protocols, V1 scope)

from typing import Protocol

class RetrievalAgent(Protocol):
    """Agent responsible for document retrieval."""
    
    def retrieve(self, query: Query, context: dict) -> RetrievalResult:
        """Retrieve relevant documents for the query."""
        ...

class GenerationAgent(Protocol):
    """Agent responsible for answer generation."""
    
    def generate(self, query: Query, context: dict) -> GenerationResult:
        """Generate an answer from query and context."""
        ...

class ValidationAgent(Protocol):
    """Agent responsible for answer validation."""
    
    def validate(self, answer: Answer, query: Query) -> ValidationResult:
        """Validate the answer against the original query."""
        ...

class CoordinatorAgent(Protocol):
    """Orchestrates other agents (V2 scope, reserved)."""
    
    def coordinate(self, query: Query) -> Answer:
        """Coordinate retrieval, generation, validation."""
        ...
```

### Current Implementation (V1)
In V1, we don't have full agent implementations. Instead, we have:
- `orchestration/engine.py` → RAGEngine (sequential pipeline, not agent-based)
- `retrieval/` → Retrieval logic (not an agent yet)
- `generation/` → Generation logic (not an agent yet)
- `security/` → Validation logic (not an agent yet)

**Do NOT implement concrete agents in V1.** Focus on completing `RAGEngine`.

---

## 2. Agent Interface Requirements

### Rule: Every Agent Protocol Must Define Clear Input/Output Types
Agent Protocols must have strict type contracts for composition to work.

### Required Components
```python
class MyAgent(Protocol):
    """My custom agent."""
    
    # 1. Clear input type
    def execute(self, input_data: AgentInput) -> AgentOutput:
        """
        Execute the agent.
        
        Args:
            input_data: AgentInput containing query, context, metadata
        
        Returns:
            AgentOutput with result, metadata, trace
        
        Raises:
            AgentError: If execution fails
        """
        ...
    
    # 2. Optional: Pre-execution hook
    def validate_input(self, input_data: AgentInput) -> bool:
        """Check if input is valid for this agent."""
        ...
    
    # 3. Optional: Status query
    def get_status(self) -> AgentStatus:
        """Return current agent status (ready, busy, error)."""
        ...
```

### Input/Output Types (from `core/models/`)
```python
from modular_rag.core.models import Query, Chunk, Answer
from modular_rag.core.models.trace import Trace, TraceStep

class AgentInput:
    query: Query
    context: dict      # Shared context (previous agent outputs)
    trace: Trace       # Shared trace for emissions
    metadata: dict     # Additional metadata

class AgentOutput:
    result: Any        # Agent-specific result type
    context: dict      # Updated context for next agent
    trace: Trace       # Updated trace
    metadata: dict     # Agent-specific metadata
```

---

## 3. State Passing Between Agents (V2 Pattern, Reserved)

### Rule: Agents Pass State via Context Dictionary
In V2+, agents will communicate via a shared context dictionary passed through the orchestrator. This pattern is **reserved** in V1 but documented for planning.

### V2+ Pattern (For Reference)
```python
# V2+ orchestrator (reserved, not implemented in V1)
def run_agent_pipeline(query: Query) -> Answer:
    context = {"query": query}  # Initial context
    trace = Trace()
    
    # Agent 1: Retrieval
    retriever_input = AgentInput(
        query=query,
        context=context,
        trace=trace
    )
    retrieval_output = retriever_agent.execute(retriever_input)
    context.update(retrieval_output.context)  # Pass to next agent
    
    # Agent 2: Generation
    generator_input = AgentInput(
        query=query,
        context=context,  # ← Includes retrieval results
        trace=trace
    )
    generation_output = generator_agent.execute(generator_input)
    context.update(generation_output.context)
    
    # Agent 3: Validation
    validator_input = AgentInput(
        query=query,
        context=context,  # ← Includes generation output
        trace=trace
    )
    validation_output = validator_agent.execute(validator_input)
    
    return validation_output.result
```

### V1 Implementation (Simplified)
In V1, the `RAGEngine` does sequential execution without agents:
```python
class RAGEngine:
    def run(self, query: Query) -> Answer:
        # Sequential, no agent composition yet
        context = self.retriever.retrieve(query)
        answer = self.generator.generate(query, context)
        return answer
```

---

## 4. TraceStep Emissions (Mandatory in Agents)

### Rule: Every Agent Action Must Emit a TraceStep
This is **non-negotiable**, even in V1 interfaces. Every implementation of an agent must emit trace data.

### Correct Pattern
```python
from modular_rag.core.models.trace import Trace, TraceStep
import time

class MyAgent:
    def execute(self, input_data: AgentInput) -> AgentOutput:
        trace = input_data.trace
        t0 = time.perf_counter()
        
        try:
            # Do agent work
            result = self._do_work(input_data.query)
            
            # Emit success trace
            trace.add_step(TraceStep(
                name=f"{self.__class__.__name__}.execute",
                latency_ms=(time.perf_counter() - t0) * 1000,
                metadata={
                    "status": "success",
                    "output_type": type(result).__name__
                }
            ))
            
            return AgentOutput(result=result, context={}, trace=trace)
        
        except Exception as e:
            # Emit failure trace
            trace.add_step(TraceStep(
                name=f"{self.__class__.__name__}.execute",
                latency_ms=(time.perf_counter() - t0) * 1000,
                metadata={
                    "status": "error",
                    "error": str(e)
                }
            ))
            raise AgentError(f"Agent failed: {e}") from e
```

---

## 5. Never Wire Agents Directly in Python

### Rule: Wire Agents Only via Manifest YAML + Registry
Even in V1, reserve the agent wiring pattern for future use.

### ❌ WRONG (Direct Python Wiring)
```python
# ❌ Do not do this (even in V1 planning)
from modular_rag.agents.retrieval_agent import MyRetrievalAgent

class Orchestrator:
    def __init__(self):
        self.retriever_agent = MyRetrievalAgent()  # ❌ Direct instantiation
```

### ✅ CORRECT (Registry + Manifest)
```python
# ✅ V1 preview: how V2+ will wire agents

# In orchestration/registry.py (add when V2 starts):
@_register_factory("MyRetrievalAgent", RetrievalAgent)
def create_retrieval_agent(config: dict) -> RetrievalAgent:
    return MyRetrievalAgent(**config)

# In manifests/my_agent_pipeline.yaml (add when V2 starts):
agents:
  retriever:
    type: "MyRetrievalAgent"
    config:
      model: "all-MiniLM-L6-v2"
```

### V1 Rule
**Do not create agent registrations in V1.** Just keep the interfaces in `contracts/agents.py`.

---

## 6. Agent Coordinator Pattern (V2 Preview)

### Rule: Coordinator Orchestrates Other Agents
In V2+, a Coordinator agent will manage the execution flow of other agents. This pattern is **reserved** in V1.

### V2+ Pattern (For Reference)
```python
class CoordinatorAgent(Protocol):
    """Orchestrates retriever, generator, validator agents."""
    
    def coordinate(self, query: Query) -> Answer:
        """
        Run the agent pipeline.
        
        Flow (for reference):
        1. Route query to appropriate agents
        2. Retrieve documents
        3. Generate answer
        4. Validate answer
        5. Return final answer
        """
        ...

# V2+ Implementation
class HierarchicalCoordinator:
    def __init__(
        self,
        retriever: RetrievalAgent,
        generator: GenerationAgent,
        validator: ValidationAgent
    ):
        self.retriever = retriever
        self.generator = generator
        self.validator = validator
    
    def coordinate(self, query: Query) -> Answer:
        trace = Trace(query_id=query.id)
        
        # Phase 1: Retrieve
        context = self.retriever.execute(
            AgentInput(query=query, context={}, trace=trace)
        ).context
        
        # Phase 2: Generate
        answer = self.generator.execute(
            AgentInput(query=query, context=context, trace=trace)
        ).result
        
        # Phase 3: Validate
        validation = self.validator.execute(
            AgentInput(query=query, context={"answer": answer}, trace=trace)
        ).result
        
        return answer if validation.is_valid else self._generate_fallback(query)
```

### V1 Status
**This is V2 scope. Do not implement in V1.** Just define the `CoordinatorAgent` Protocol in `contracts/agents.py` and leave it at that.

---

## 7. Agent Error Handling

### Rule: Agents Must Raise Custom Errors, Never Silence Failures
Agents must be strict about error propagation for debugging.

### Correct Pattern
```python
from modular_rag.core.errors import AgentError

class MyAgent:
    def execute(self, input_data: AgentInput) -> AgentOutput:
        try:
            result = self._execute_logic(input_data)
            return AgentOutput(result=result, context={})
        except ValueError as e:
            raise AgentError(f"Invalid input: {e}") from e
        except Exception as e:
            raise AgentError(f"Agent execution failed: {e}") from e
```

### Error Types
```python
AgentError              # Generic agent error
ValidationError        # Validation failed
ExecutionError         # Execution failed
StateError            # Invalid state transition
```

---

## 8. Testing Agents

### Unit Tests (V1 Scope)
Test the Protocol conformance in `tests/contract/test_agents_conformance.py`:

```python
# tests/contract/test_agents_conformance.py
import pytest
from modular_rag.contracts.agents import RetrievalAgent, GenerationAgent

def test_retrieval_agent_protocol():
    """Verify RetrievalAgent Protocol is defined."""
    # In V1, we just check the Protocol exists
    assert hasattr(RetrievalAgent, "retrieve")

def test_generation_agent_protocol():
    """Verify GenerationAgent Protocol is defined."""
    assert hasattr(GenerationAgent, "generate")
```

### Integration Tests (V2+)
When agents are implemented in V2+, add integration tests:

```python
# tests/integration/test_agent_coordination.py (V2 scope)
@pytest.mark.integration
def test_coordinator_runs_full_pipeline():
    """Test coordinator orchestrating all agents."""
    coordinator = HierarchicalCoordinator(
        retriever=mock_retriever,
        generator=mock_generator,
        validator=mock_validator
    )
    answer = coordinator.coordinate(query)
    assert answer.text
    assert len(answer.trace.steps) >= 3  # retrieve, generate, validate
```

---

## 9. Agent Configuration (Via Manifest YAML)

### Rule: All Agent Parameters Come from Manifest
No hardcoded agent configurations.

### V2+ Example
```yaml
# manifests/agentic-rag.yaml (V2 scope)
agents:
  retriever:
    type: "VectorRetrievalAgent"
    config:
      retriever_k: 10
      reranker_k: 5
  
  generator:
    type: "OpenAIGenerationAgent"
    config:
      model: "gpt-4"
      temperature: 0.7
  
  validator:
    type: "GroundednessValidator"
    config:
      threshold: 0.8

coordinator:
  type: "HierarchicalCoordinator"
  config:
    agent_order: ["retriever", "generator", "validator"]
```

---

## 10. Summary: Agents Module (V1 vs V2+)

### V1 Scope
- ✅ Define Protocols: `RetrievalAgent`, `GenerationAgent`, `ValidationAgent`, `CoordinatorAgent`
- ✅ Define `AgentInput`, `AgentOutput` types in `core/models/`
- ✅ Document agent patterns for V2+ planning
- ✅ Test Protocol existence

### V2+ Scope
- ⏸️ Implement concrete agents (HierarchicalRetriever, DynamicGenerator, etc.)
- ⏸️ Implement Coordinator orchestration
- ⏸️ Agent wiring via Registry + manifest YAML
- ⏸️ Multi-turn interactions
- ⏸️ Tool use patterns

### V1 Rule
**Do not implement agents beyond Protocols. Focus on completing `RAGEngine` in V1.**

---

## 11. Questions Before Editing Agents

Before modifying this module, ask yourself:
1. **Is this V1 or V2?** (V1: Protocols only. V2: Implementations.)
2. **Does this require a Protocol in `contracts/`?** (Yes, always.)
3. **Am I defining behavior or just interface?** (V1: interface only.)
4. **Will this break the current `RAGEngine`?** (If yes, wait for V2.)
5. **Have I updated `tests/contract/test_agents_conformance.py`?** (If adding Protocol.)

---

Good luck working with agents!
