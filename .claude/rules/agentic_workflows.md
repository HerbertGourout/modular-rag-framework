---
paths:
  - "src/modular_rag/agents/**/*.py"
description: "Agentic workflows: coordination patterns, tool use, multi-turn interactions. V1 reserved, V2+ implementation scope."
version: "1.0"
lastUpdated: "2026-06-22"
---

# Règles — Agentic Workflows (V2+ Reserved)

This file documents **patterns and design guidelines for agentic workflows**, which are V2+ scope. In V1, **no agentic workflow implementations are added**. This document serves as a design reference for future development.

---

## 1. What Are Agentic Workflows?

### Definition
Agentic workflows extend V1's sequential RAG pipeline (query → retrieve → generate) into flexible, multi-turn agent-based orchestration where:
- **Agents** are autonomous executors (Retriever, Generator, Validator, Planner, etc.)
- **Workflows** define how agents interact (serial, parallel, conditional, looping)
- **Tools** extend agent capabilities (search, calculation, external APIs)
- **State** is passed and evolved through the pipeline

### V1 vs V2+ Comparison

| Aspect | V1 (Current) | V2+ (Agentic) |
|--------|---|---|
| **Pipeline** | Sequential: retrieve → generate | Flexible: agent graphs with routing |
| **Agents** | None (monolithic RAGEngine) | Multiple specialized agents |
| **Coordination** | Fixed RAGEngine | Dynamic Coordinator |
| **Interactions** | Single turn | Multi-turn support |
| **Tools** | Retrieval, generation, guards | Extensible tool ecosystem |
| **State** | Query → Context → Answer | Evolving context through agents |
| **Error Handling** | Fallbacks (BM25 for no results) | Full recovery strategies |

### Scope Decision (Why V2+?)
V2+ agentic workflows are **complex and foundational**. Implementing them prematurely could break V1 completion. The order is:
1. **V1** (current): Complete `RAGEngine` + `examples/simple_qa/` end-to-end
2. **V2**: Agentic orchestration (agents, coordination, multi-turn)
3. **V3**: Graph memory (knowledge graph store, versioning)
4. **V4**: Governance (audit, compliance, policy engines)
5. **V5**: Multimodal (images, video, audio)

---

## 2. Agentic Architecture (V2+ Design)

### Agent Types (Planned for V2)
```
Planner Agent
├── Determines task decomposition
├── Routes query to specialized agents
└── Fallback routing on errors

Retriever Agent
├── Queries vector/BM25 indices
├── Reranks results
└── Returns ranked documents

Generator Agent
├── Takes query + context
├── Generates citations
├── Validates groundedness
└── Returns answer with metadata

Validator Agent
├── Checks answer quality
├── Verifies factuality
├── Rates confidence
└── Triggers refinement if needed

Tool Agent (V2+)
├── Extends with external tools
├── Web search, calculation, APIs
├── Manages tool state
└── Handles failures
```

### Agent Composition Pattern (V2+ Example, Not Implemented in V1)
```python
# V2+ pseudocode (not implemented)
class WorkflowOrchestrator:
    def __init__(self, agents: dict[str, Agent], tools: dict[str, Tool]):
        self.agents = agents      # Specialized agents
        self.tools = tools        # Tool suite
        self.state = {}           # Shared workflow state
    
    def run_workflow(self, query: Query) -> Answer:
        # Multi-step agentic workflow
        task_plan = self.agents["planner"].plan(query)
        
        for task in task_plan.subtasks:
            if task.type == "retrieve":
                results = self.agents["retriever"].retrieve(task)
                self.state["retrieval_results"] = results
            elif task.type == "generate":
                answer = self.agents["generator"].generate(
                    query=query,
                    context=self.state["retrieval_results"],
                    plan=task_plan
                )
                self.state["answer"] = answer
            elif task.type == "validate":
                validation = self.agents["validator"].validate(answer)
                self.state["validation"] = validation
            elif task.requires_tool:
                tool_result = self.tools[task.tool_name].execute(task)
                self.state[task.tool_name] = tool_result
        
        return self.state["answer"]
```

---

## 3. Decision Trees & Routing (V2+ Pattern)

### Router Logic (V2+ Example)
```python
# V2+ pseudocode (not implemented)
class QueryRouter:
    def route(self, query: Query) -> RoutingDecision:
        """Route query to optimal agent path."""
        
        # Decision 1: Complexity analysis
        if query.complexity == "simple":
            return RoutingDecision(
                strategy="direct_retrieval",
                agents=["retriever", "generator"]
            )
        elif query.complexity == "complex":
            return RoutingDecision(
                strategy="multi_agent_planning",
                agents=["planner", "retriever", "generator", "validator"]
            )
        
        # Decision 2: Domain routing
        if query.domain == "math":
            return RoutingDecision(
                strategy="retrieval_with_calculation",
                tools=["calculator"],
                agents=["retriever", "generator"]
            )
        elif query.domain == "current_events":
            return RoutingDecision(
                strategy="retrieval_with_web_search",
                tools=["web_search"],
                agents=["retriever", "generator"]
            )
        
        return RoutingDecision(strategy="default_hybrid")
```

### Fallback Strategies (V2+ Example)
```python
# V2+ pseudocode
if primary_strategy_fails:
    fallback_strategies = [
        "hybrid_retrieval",      # Try hybrid if vector fails
        "bm25_fallback",         # Try BM25 if hybrid fails
        "external_knowledge",    # Try knowledge base if BM25 fails
        "clarification_prompt"   # Ask user for clarification
    ]
    
    for strategy in fallback_strategies:
        try:
            result = execute_strategy(query, strategy)
            if is_acceptable(result):
                return result
        except StrategyError:
            continue
    
    return Answer(text="Unable to answer. Please rephrase.", confidence=0.0)
```

---

## 4. Tool Use Patterns (V2+ Reserved)

### Tool Interface (V2+ Design)
```python
# V2+ pseudocode (contracts/tools.py, not yet created)
class Tool(Protocol):
    """Interface for agent tools."""
    
    def execute(self, input_data: ToolInput) -> ToolOutput:
        """Execute the tool."""
        ...
    
    def validate_input(self, input_data: ToolInput) -> bool:
        """Check if input is valid."""
        ...

# Tool Examples (V2+ planned)
class WebSearchTool(Tool):
    """Search the web for current information."""
    def execute(self, query: str) -> list[SearchResult]:
        ...

class CalculatorTool(Tool):
    """Perform mathematical calculations."""
    def execute(self, expression: str) -> float:
        ...

class APICallTool(Tool):
    """Call external REST APIs."""
    def execute(self, url: str, method: str, params: dict) -> dict:
        ...
```

### Tool Integration (V2+ Example)
```python
# V2+ pseudocode (not implemented)
class ToolUseAgent:
    def __init__(self, tools: dict[str, Tool]):
        self.tools = tools
    
    def execute_with_tools(self, query: Query) -> Answer:
        """Execute query with tool availability."""
        
        # Ask LLM which tool to use
        tool_decision = self.llm.decide_tool(query)  # e.g., "web_search"
        
        if tool_decision.tool_name:
            tool = self.tools[tool_decision.tool_name]
            tool_result = tool.execute(tool_decision.tool_input)
            
            # Re-query LLM with tool result
            return self.llm.generate_with_context(
                query=query,
                context=tool_result
            )
        else:
            # No tool needed, generate directly
            return self.llm.generate(query)
```

---

## 5. Multi-Turn Interactions (V2+ Reserved)

### Context Persistence (V2+ Pattern)
```python
# V2+ pseudocode (not implemented)
class ConversationState:
    """Persistent state across turns."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.turns: list[Turn] = []
        self.shared_context: dict = {}
        self.memory: Memory = Memory()
    
    def add_turn(self, user_query: str, answer: Answer):
        """Record a turn in the conversation."""
        self.turns.append(Turn(
            user_query=user_query,
            answer=answer,
            timestamp=now()
        ))
    
    def get_context(self) -> dict:
        """Get context for next turn (previous Q&A, entities, etc.)."""
        return {
            "previous_turns": self.turns[-3:],  # Last 3 turns
            "entities": self._extract_entities(),
            "topics": self._extract_topics(),
            "memory": self.memory.recall()
        }

class MultiTurnOrchestrator:
    """Orchestrate multi-turn conversations."""
    
    def run_conversation(self, session_id: str):
        state = ConversationState(session_id)
        
        while True:
            user_query = input("You: ")
            
            # Augment query with conversation context
            augmented_query = self._augment_with_history(
                user_query,
                state.get_context()
            )
            
            # Run single-turn pipeline
            answer = self.orchestrator.run(augmented_query)
            
            # Store for next turn
            state.add_turn(user_query, answer)
            
            # Update memory
            state.memory.store(user_query, answer)
            
            print(f"Assistant: {answer.text}")
```

---

## 6. Error Handling & Recovery (V2+ Strategy)

### Robust Agent Composition (V2+ Pattern)
```python
# V2+ pseudocode (not implemented)
class RobustAgentPipeline:
    def run_with_recovery(self, query: Query, max_retries: int = 3) -> Answer:
        """Run pipeline with automatic recovery."""
        
        for attempt in range(max_retries):
            try:
                # Attempt standard flow
                return self.run_agents(query)
            
            except AgentError as e:
                # Log and attempt recovery
                logger.warning(f"Agent error (attempt {attempt+1}): {e}")
                
                # Recovery strategy depends on which agent failed
                if isinstance(e, RetrievalError):
                    # Fallback: use vector search instead of hybrid
                    return self.run_agents_fallback(query, skip_hybrid=True)
                elif isinstance(e, GenerationError):
                    # Fallback: use smaller model
                    return self.run_agents_fallback(query, model="gpt-3.5")
                elif isinstance(e, ValidationError):
                    # Fallback: lower confidence threshold
                    return self.run_agents_fallback(query, confidence_threshold=0.5)
                
                # If fallback also fails, try next attempt
                continue
            
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    continue
                else:
                    # Final fallback: return degraded response
                    return Answer(
                        text="I encountered an error processing your query.",
                        confidence=0.0,
                        is_fallback=True
                    )
        
        raise PipelineError("Pipeline failed after all retries")
```

---

## 7. State Management (V2+ Architecture)

### Agent Context Passing
```python
# V2+ pseudocode
class AgentContext:
    """Shared context passed through agent pipeline."""
    
    def __init__(self, query: Query):
        self.query = query
        self.retrieval_results: list[Chunk] = []
        self.generated_answer: Answer = None
        self.validation_result: ValidationResult = None
        self.metadata: dict = {}
        self.trace: Trace = Trace()
    
    def pass_to_next_agent(self, agent_name: str) -> AgentInput:
        """Prepare context for next agent."""
        return AgentInput(
            query=self.query,
            context={
                "retrieval_results": self.retrieval_results,
                "generated_answer": self.generated_answer,
                "validation": self.validation_result,
                "metadata": self.metadata
            },
            trace=self.trace
        )
```

---

## 8. V1 Actions: What NOT to Do

### ❌ Do NOT in V1
- ❌ Create agent implementations (except Protocols in `contracts/`)
- ❌ Implement multi-turn logic
- ❌ Add tool use patterns
- ❌ Create decision trees or complex routers
- ❌ Implement ConversationState or context persistence
- ❌ Wire agents via manifest YAML
- ❌ Create new top-level modules for agents

### ✅ DO in V1
- ✅ Document agent patterns in this file
- ✅ Define Protocols in `contracts/agents.py`
- ✅ Complete `RAGEngine` sequential flow
- ✅ Run `examples/simple_qa/` end-to-end
- ✅ Test V1 scope with `pytest tests/unit tests/contract`

---

## 9. References for V2+ Planning

### Related Architecture Decisions
- [ADR-0001: Modular Architecture](../adr/0001-modular-architecture.md) — Layer boundaries
- [ADR-0002: Contracts & Plugins](../adr/0002-contracts-and-plugins.md) — Protocol pattern
- [ADR-0003: Security & Governance](../adr/0003-security-and-governance.md) — Policy enforcement

### Related Documentation
- [Plugin Development Guide](../guides/plugin-development.md) — How to extend framework
- [Module Model](../architecture/module-model.md) — Architecture deep-dive
- [CLAUDE.md Section 09](../../CLAUDE.md#09--compact-instructions-known-stubs) — Known stubs

### Examples (V1 Only)
- `examples/simple_qa/` — V1 end-to-end example (no agents yet)
- `examples/agentic_rag/` — V2+ planning skeleton (not implemented)

---

## 10. Summary: Agentic Workflows

### Current Status (V1)
```
✅ Designed:     Patterns, interfaces, guidelines documented
✅ Planned:      Agent types, tool interfaces, multi-turn flows
⏸️ Implemented:  NONE (V2+ scope)
🚫 In V1:        Focus on RAGEngine, not agents
```

### Timeline
- **V1** (current): RAGEngine, retrievers, generators, guards
- **V2** (planned): Agent orchestration, tools, multi-turn
- **V3+** (future): Graph memory, governance, multimodal

### When to Revisit
- After `examples/simple_qa/` runs end-to-end
- After V1 tests (`pytest tests/unit tests/contract`) pass
- After stakeholder sign-off on V1 scope
- Then ADR-0002 extension for agentic patterns

---

## 11. Questions on Agentic Workflows?

If you encounter questions about agentic workflows in V1:

1. **"Should I implement agent orchestration?"** → No. V2 scope. Document the pattern instead.
2. **"How do I extend agents?"** → Wait for V2. V1 has only Protocols in `contracts/agents.py`.
3. **"Where does tool use go?"** → V2+ scope. Reserve `contracts/tools.py` for later.
4. **"What about multi-turn?"** → V2+ scope. V1 is single-turn only.
5. **"Can I add agent state?"** → Document in this file for V2+. Don't implement in V1.

**Answer: If it's not in `examples/simple_qa/`, it's V2+ scope. Ask the user if unsure.**

---

Good luck planning V2+ agentic workflows!
