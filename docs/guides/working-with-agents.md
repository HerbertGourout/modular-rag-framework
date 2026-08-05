# Extending the Framework with Agents (V2+ Guide)

> **⚠️ Superseded by [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) (accepted
> 2026-08-04).** Generic multi-agent orchestration is now **delegated** to a selected external
> engine, not built natively along the lines this guide describes. The five prototype agent
> classes it references (`CoordinatorAgent`, `RetrieverAgent`, `ExtractorAgent`,
> `SynthesizerAgent`, `ValidatorAgent`) were removed in Lot 17
> (`docs/refactoring-plan.md`) — zero test coverage, zero consumers anywhere in the codebase.
> Retained here as a historical design reference, not an implementation guide: if you land here
> to build something in `agents/`, it should be an adapter that calls the external engine
> (`DocumentEngine` port, `contracts/engine.py`, Lot 7), not the coordinator/tool-use runtime
> described below.

This guide explains how to extend the Modular RAG Framework with agent-based orchestration when you're ready for V2+.

---

## Table of Contents
1. [When to Use This Guide](#when-to-use-this-guide)
2. [Agent Architecture Overview](#agent-architecture-overview)
3. [Defining Agent Protocols](#defining-agent-protocols)
4. [Implementing Concrete Agents](#implementing-concrete-agents)
5. [Orchestration Patterns](#orchestration-patterns)
6. [Multi-Turn Conversations](#multi-turn-conversations)
7. [Tool Integration](#tool-integration)
8. [Testing Agents](#testing-agents)
9. [Common Patterns & Anti-Patterns](#common-patterns--anti-patterns)

---

## When to Use This Guide

### ✅ Use This Guide If:
- You've completed V1 (RAGEngine, retrievers, generators, guards)
- You want multi-agent orchestration (Planner, Retriever, Generator, Validator agents)
- You need multi-turn conversation support
- You want to extend agents with tools (web search, APIs, calculators)

### ❌ Do NOT Use This Guide If:
- You're still on V1 (single-turn RAGEngine)
- You're just extending retrievers or generators (those are domain modules, not agents)
- You're adding new adapters (see `.claude/rules/adapters.md`)

**See also**: [CLAUDE.md section 09](../../CLAUDE.md#09--known-stubs--v2-scope) for V1 vs V2+ scope.

---

## Agent Architecture Overview

### V1 Architecture (Current)
```
Query
  ↓
┌─────────────────────────────────────────┐
│         RAGEngine (Sequential)          │
│  1. Guard query                         │
│  2. Retrieve context                    │
│  3. Generate answer                     │
│  4. Return answer                       │
└─────────────────────────────────────────┘
  ↓
Answer
```

### V2+ Architecture (Future)
```
Query
  ↓
┌─────────────────────────────────────────┐
│        Coordinator (Agent Graph)         │
│  ┌─────────────────────────────────┐   │
│  │  Planner Agent                  │   │
│  │  → Decompose query              │   │
│  │  → Route to agents              │   │
│  └─────────────────────────────────┘   │
│           ↓                              │
│  ┌─────────────────────────────────┐   │
│  │  Retriever Agent                │   │
│  │  → Query vector/BM25            │   │
│  │  → Rerank results               │   │
│  └─────────────────────────────────┘   │
│           ↓                              │
│  ┌─────────────────────────────────┐   │
│  │  Generator Agent                │   │
│  │  → Generate with context        │   │
│  │  → Add citations                │   │
│  └─────────────────────────────────┘   │
│           ↓                              │
│  ┌─────────────────────────────────┐   │
│  │  Validator Agent                │   │
│  │  → Check quality/confidence     │   │
│  │  → Trigger refinement if needed │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
  ↓
Answer with Metadata
```

---

## Defining Agent Protocols

### Step 1: Create Protocol in `contracts/agents.py`

```python
# src/modular_rag/contracts/agents.py

from typing import Protocol
from modular_rag.core.models import Query, Answer, Chunk
from modular_rag.core.models.trace import Trace

class AgentInput:
    """Input passed to an agent."""
    query: Query
    context: dict          # Shared context from previous agents
    trace: Trace           # Shared trace for emissions

class AgentOutput:
    """Output from an agent."""
    result: Any            # Agent-specific result
    context: dict          # Updated context for next agent
    trace: Trace           # Updated trace

class RetrievalAgent(Protocol):
    """Agent responsible for document retrieval."""
    
    def retrieve(self, input_data: AgentInput) -> AgentOutput:
        """
        Retrieve relevant documents for the query.
        
        Args:
            input_data: AgentInput with query, context, trace
        
        Returns:
            AgentOutput with retrieved chunks in context["chunks"]
        """
        ...

class GenerationAgent(Protocol):
    """Agent responsible for answer generation."""
    
    def generate(self, input_data: AgentInput) -> AgentOutput:
        """
        Generate an answer from query and context.
        
        Args:
            input_data: AgentInput with query, context["chunks"], trace
        
        Returns:
            AgentOutput with Answer in result
        """
        ...

class ValidationAgent(Protocol):
    """Agent responsible for answer validation."""
    
    def validate(self, input_data: AgentInput) -> AgentOutput:
        """
        Validate the answer against the original query.
        
        Args:
            input_data: AgentInput with Answer in context["answer"]
        
        Returns:
            AgentOutput with ValidationResult in result
        """
        ...

class CoordinatorAgent(Protocol):
    """Orchestrates other agents."""
    
    def coordinate(self, query: Query) -> Answer:
        """
        Run the full agent pipeline.
        
        Args:
            query: User query
        
        Returns:
            Final answer after all agents process it
        """
        ...
```

---

## Implementing Concrete Agents

### Step 2: Create Agent Implementations

#### Retrieval Agent Example
```python
# src/modular_rag/agents/retriever_agent.py

from modular_rag.contracts.agents import RetrievalAgent, AgentInput, AgentOutput
from modular_rag.contracts.retrieval import Retriever
from modular_rag.core.models.trace import TraceStep
import time

class VectorRetrievalAgent(RetrievalAgent):
    """Agent that retrieves documents using vector search."""
    
    def __init__(self, retriever: Retriever, k: int = 10):
        self.retriever = retriever
        self.k = k
    
    def retrieve(self, input_data: AgentInput) -> AgentOutput:
        t0 = time.perf_counter()
        
        # Retrieve
        chunks = self.retriever.retrieve(input_data.query, k=self.k)
        
        # Emit trace
        input_data.trace.add_step(TraceStep(
            name="VectorRetrievalAgent.retrieve",
            latency_ms=(time.perf_counter() - t0) * 1000,
            metadata={"chunks_retrieved": len(chunks)}
        ))
        
        # Return
        return AgentOutput(
            result=chunks,
            context={"chunks": chunks},
            trace=input_data.trace
        )
```

#### Generator Agent Example
```python
# src/modular_rag/agents/generator_agent.py

from modular_rag.contracts.agents import GenerationAgent, AgentInput, AgentOutput
from modular_rag.contracts.generation import Generator
from modular_rag.core.models.trace import TraceStep
import time

class StandardGenerationAgent(GenerationAgent):
    """Agent that generates answers from query + context."""
    
    def __init__(self, generator: Generator):
        self.generator = generator
    
    def generate(self, input_data: AgentInput) -> AgentOutput:
        t0 = time.perf_counter()
        
        # Extract context
        chunks = input_data.context.get("chunks", [])
        
        # Generate
        answer = self.generator.generate(
            query=input_data.query,
            context=chunks,
            trace=input_data.trace
        )
        
        # Emit trace
        input_data.trace.add_step(TraceStep(
            name="StandardGenerationAgent.generate",
            latency_ms=(time.perf_counter() - t0) * 1000,
            metadata={"tokens": answer.token_count}
        ))
        
        # Return
        return AgentOutput(
            result=answer,
            context={"answer": answer},
            trace=input_data.trace
        )
```

---

## Orchestration Patterns

### Pattern 1: Sequential Orchestration (Simple)
```python
# src/modular_rag/orchestration/sequential_coordinator.py

from modular_rag.contracts.agents import CoordinatorAgent
from modular_rag.core.models import Query, Answer
from modular_rag.core.models.trace import Trace

class SequentialCoordinator(CoordinatorAgent):
    """Run agents in sequence: Planner → Retriever → Generator → Validator."""
    
    def __init__(
        self,
        retriever_agent: RetrievalAgent,
        generator_agent: GenerationAgent,
        validator_agent: ValidationAgent
    ):
        self.retriever = retriever_agent
        self.generator = generator_agent
        self.validator = validator_agent
    
    def coordinate(self, query: Query) -> Answer:
        trace = Trace(query_id=query.id)
        context = {"query": query}
        
        # Step 1: Retrieve
        retrieval_input = AgentInput(query=query, context=context, trace=trace)
        retrieval_output = self.retriever.retrieve(retrieval_input)
        context.update(retrieval_output.context)
        trace = retrieval_output.trace
        
        # Step 2: Generate
        generation_input = AgentInput(query=query, context=context, trace=trace)
        generation_output = self.generator.generate(generation_input)
        context.update(generation_output.context)
        trace = generation_output.trace
        
        # Step 3: Validate
        validation_input = AgentInput(query=query, context=context, trace=trace)
        validation_output = self.validator.validate(validation_input)
        
        # Return answer with full trace
        answer = validation_output.result
        answer.trace = validation_output.trace
        return answer
```

### Pattern 2: Conditional Routing
```python
# src/modular_rag/orchestration/conditional_coordinator.py

class ConditionalCoordinator(CoordinatorAgent):
    """Route agents based on query analysis."""
    
    def coordinate(self, query: Query) -> Answer:
        trace = Trace(query_id=query.id)
        context = {"query": query}
        
        # Analyze query
        query_complexity = self._analyze_complexity(query)
        
        if query_complexity == "simple":
            # Simple query: direct retrieval + generation
            context = self._retrieve_and_generate(query, context, trace)
        elif query_complexity == "complex":
            # Complex query: multi-step with planning
            context = self._plan_and_execute(query, context, trace)
        else:
            # Unknown: fallback to simple
            context = self._retrieve_and_generate(query, context, trace)
        
        answer = context["answer"]
        answer.trace = trace
        return answer
    
    def _analyze_complexity(self, query: Query) -> str:
        """Determine query complexity."""
        word_count = len(query.text.split())
        if word_count < 10:
            return "simple"
        elif word_count < 30:
            return "medium"
        else:
            return "complex"
```

---

## Multi-Turn Conversations

### Maintaining Conversation State
```python
# src/modular_rag/orchestration/conversation_state.py

class ConversationState:
    """Persistent state across multiple turns."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.turns = []  # History of (query, answer) pairs
        self.entities = {}  # Extracted entities (names, dates, etc.)
        self.topics = []  # Topics discussed
        self.memory = {}  # Key-value memory
    
    def add_turn(self, query: Query, answer: Answer):
        """Record a turn in the conversation."""
        self.turns.append((query, answer))
        self._extract_entities(answer)
        self._extract_topics(answer)
    
    def get_context_for_next_turn(self) -> dict:
        """Get context to augment the next query."""
        return {
            "previous_turns": self.turns[-3:],  # Last 3 turns
            "entities": self.entities,
            "topics": self.topics,
            "memory": self.memory
        }

class MultiTurnCoordinator(CoordinatorAgent):
    """Handle multi-turn conversations."""
    
    def __init__(self, session_id: str, coordinator: CoordinatorAgent):
        self.state = ConversationState(session_id)
        self.coordinator = coordinator
    
    def coordinate(self, query: Query) -> Answer:
        # Augment query with conversation history
        augmented_query = self._augment_query(
            query,
            self.state.get_context_for_next_turn()
        )
        
        # Run single-turn pipeline with augmented query
        answer = self.coordinator.coordinate(augmented_query)
        
        # Store turn for next iteration
        self.state.add_turn(query, answer)
        
        return answer
    
    def _augment_query(self, query: Query, context: dict) -> Query:
        """Add conversation context to the query."""
        previous_context = f"\nPrevious discussion: {context['previous_turns']}"
        augmented_text = query.text + previous_context
        return Query(text=augmented_text, metadata=query.metadata)
```

---

## Tool Integration

### Tool Interface
```python
# src/modular_rag/contracts/tools.py (NEW for V2+)

from typing import Protocol

class Tool(Protocol):
    """Interface for agent tools."""
    
    def execute(self, input_data: dict) -> dict:
        """
        Execute the tool with given input.
        
        Args:
            input_data: Tool-specific input dict
        
        Returns:
            Tool-specific output dict
        """
        ...
    
    def validate_input(self, input_data: dict) -> bool:
        """Check if input is valid for this tool."""
        ...

class WebSearchTool(Tool):
    """Search the web for current information."""
    
    def execute(self, input_data: dict) -> dict:
        query = input_data["query"]
        results = self._search_web(query)
        return {"results": results}

class CalculatorTool(Tool):
    """Perform mathematical calculations."""
    
    def execute(self, input_data: dict) -> dict:
        expression = input_data["expression"]
        result = eval(expression)  # In production, use safe evaluator
        return {"result": result}
```

### Tool-Using Agent
```python
# src/modular_rag/agents/tool_using_agent.py

class ToolUsingGenerationAgent(GenerationAgent):
    """Generation agent that can use tools."""
    
    def __init__(self, generator: Generator, tools: dict[str, Tool]):
        self.generator = generator
        self.tools = tools
    
    def generate(self, input_data: AgentInput) -> AgentOutput:
        # Ask LLM which tool to use
        tool_decision = self.generator.decide_tool(input_data.query)
        
        if tool_decision.tool_name:
            # Execute tool
            tool = self.tools[tool_decision.tool_name]
            tool_result = tool.execute(tool_decision.tool_input)
            
            # Re-generate with tool result
            enhanced_context = input_data.context.copy()
            enhanced_context["tool_result"] = tool_result
            
            input_data.context = enhanced_context
            return self.generator.generate(input_data)
        else:
            # No tool needed
            return self.generator.generate(input_data)
```

---

## Testing Agents

### Unit Tests
```python
# tests/unit/agents/test_retrieval_agent.py

import pytest
from unittest.mock import MagicMock
from modular_rag.agents.retriever_agent import VectorRetrievalAgent
from modular_rag.core.models import Query
from modular_rag.core.models.trace import Trace

def test_retrieval_agent_emits_trace():
    """Verify retrieval agent emits trace step."""
    # Mock retriever
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [MagicMock(), MagicMock()]
    
    agent = VectorRetrievalAgent(mock_retriever)
    
    # Execute
    query = Query(text="What is RAG?")
    trace = Trace()
    input_data = AgentInput(query=query, context={}, trace=trace)
    output = agent.retrieve(input_data)
    
    # Verify
    assert len(output.trace.steps) > 0
    assert output.trace.steps[0].name == "VectorRetrievalAgent.retrieve"
```

### Integration Tests (With Real Services)
```python
# tests/integration/agents/test_agent_coordination.py

import pytest

@pytest.mark.integration
def test_sequential_coordinator_end_to_end():
    """Test coordinator with real retriever, generator, validator."""
    coordinator = SequentialCoordinator(
        retriever_agent=VectorRetrievalAgent(real_retriever),
        generator_agent=StandardGenerationAgent(real_generator),
        validator_agent=GroundednessValidator()
    )
    
    query = Query(text="What is machine learning?")
    answer = coordinator.coordinate(query)
    
    assert answer.text
    assert len(answer.trace.steps) >= 3  # retrieval, generation, validation
```

---

## Common Patterns & Anti-Patterns

### ✅ Good Pattern: State Passing via Context
```python
# ✅ Good: agents pass state via context dict
output = agent.retrieve(input_data)
updated_context = output.context
output2 = next_agent.generate(
    AgentInput(..., context=updated_context, trace=output.trace)
)
```

### ❌ Bad Pattern: Direct Instantiation
```python
# ❌ Bad: agents instantiate each other
class CoordinatorAgent:
    def coordinate(self, query):
        retriever = VectorRetrievalAgent(...)  # Direct instantiation!
        generator = StandardGenerationAgent(...)
        validator = GroundednessValidator(...)
```

### ✅ Good Pattern: Registry + Manifest
```python
# ✅ Good: agents wired via registry + manifest
# In orchestration/registry.py:
@_register_factory("VectorRetrievalAgent", RetrievalAgent)
def create_retrieval_agent(config):
    return VectorRetrievalAgent(**config)

# In manifest YAML:
agents:
  retriever:
    type: "VectorRetrievalAgent"
    config:
      k: 10
```

### ❌ Bad Pattern: Hardcoded Agent Selection
```python
# ❌ Bad: hardcoded agent selection
if query_domain == "math":
    agent = CalculatorAgent()  # Hardcoded!
elif query_domain == "web":
    agent = WebSearchAgent()
```

---

## Wiring Agents in Manifest

### Example: Agent Pipeline YAML (V2+)
```yaml
# manifests/agentic-rag.yaml (V2+ scope, reserved)

components:
  chunker:
    type: "FixedSizeChunker"
    config:
      chunk_size: 512
  
  retriever:
    type: "VectorRetriever"
    config:
      k: 10

agents:
  retriever_agent:
    type: "VectorRetrievalAgent"
    config:
      retriever_key: "retriever"
      k: 10
  
  generator_agent:
    type: "StandardGenerationAgent"
    config:
      generator_key: "generator"
  
  validator_agent:
    type: "GroundednessValidator"
    config:
      threshold: 0.8

coordinator:
  type: "SequentialCoordinator"
  config:
    agents:
      - retriever_agent
      - generator_agent
      - validator_agent
```

---

## Next Steps

1. **Complete V1** → `examples/simple_qa/` end-to-end
2. **Lock V1 tests** → `pytest tests/unit tests/contract` at 100%
3. **Start V2 planning** → Use patterns from this guide
4. **Implement agents incrementally** → Start with SequentialCoordinator
5. **Add multi-turn support** → Implement ConversationState
6. **Integrate tools** → Add Tool protocol + tool-using agents
7. **Test extensively** → Unit + integration tests for all agents

---

## References

- [.claude/rules/agents.md](../../.claude/rules/agents.md) — Agent rules & constraints
- [.claude/rules/agentic_workflows.md](../../.claude/rules/agentic_workflows.md) — V2+ workflow patterns
- [ADR-0002: Contracts and Plugin Pattern](../adr/0002-contracts-and-plugins.md) — How to extend framework
- [src/modular_rag/contracts/agents.py](../../src/modular_rag/contracts/agents.py) — Protocol definitions (V2+)

Good luck extending with agents!
