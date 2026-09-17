---
title: "Claude Code Specialized Subagents"
description: "8 domain-specialized agents for RAG framework development"
version: "1.0"
created: "2026-06-21"
applicableScopes: ["All Development", "Architecture", "Testing", "Production"]
---

# Claude Code Specialized Subagents

**For**: All developers  
**Purpose**: Invoke domain-specific AI experts for RAG framework work  
**Updated**: June 21, 2026  
**Status**: Production Ready ✅

This document describes the **8 research-paper-driven subagents** available in Claude Code for Modular RAG Framework development.

---

## Quick Reference

| Subagent | Purpose | Invocation | When to Use |
|----------|---------|-----------|------------|
| **retrieval-specialist** | Vector search, BM25, fusion, ranking | `@retrieval-specialist` | Building/optimizing retrievers |
| **ingestion-specialist** | Document processing, chunking, preprocessing | `@ingestion-specialist` | Designing ingestion pipelines |
| **generation-specialist** | LLM selection, prompt engineering, multi-model | `@generation-specialist` | Building generators, prompt optimization |
| **security-specialist** | Guards, PII redaction, compliance | `@security-specialist` | Implementing security layers |
| **architecture-reviewer** | Layering validation, imports, design patterns | `@architecture-reviewer` | Code review, architecture compliance |
| **test-specialist** | Test design, coverage, quality metrics | `@test-specialist` | Test strategy, quality optimization |
| **orchestration-specialist** | Registry patterns, manifest-driven wiring | `@orchestration-specialist` | Component orchestration design |
| **observability-expert** | Tracing, metrics, performance analysis | `@observability-expert` | Observability architecture, debugging |

---

## 1. retrieval-specialist

**Domain Expertise**: Vector search, BM25, hybrid fusion, reranking, ranking algorithms

### Capabilities

✅ Design vector retrieval strategies (Dense Passage Retrieval, ColBERT patterns)  
✅ Optimize BM25 indexing (tokenization, stemming, field weighting)  
✅ Implement hybrid fusion (Reciprocal Rank Fusion, weighted combination)  
✅ Reranking strategies (cross-encoder, diversity, query-aware)  
✅ Vector-to-metadata mapping and dense-sparse coordination  
✅ Performance optimization (caching, indexing, query expansion)  

### When to Use

- **Building retrievers**: Implementing new vector/BM25/graph retrievers
- **Fusion design**: Combining multiple retrieval signals
- **Optimization**: Improving precision/recall, reducing latency
- **Ranking**: Implementing cross-encoder reranking

### Expertise Areas

- **Algorithms**: DPR, BM25+, ColBERT, RRF, Noriega fusion, TF-IDF variants
- **Patterns**: Async fan-out/fan-in for parallel retrieval
- **Performance**: Indexing optimization, query expansion, caching
- **Edge cases**: Out-of-vocabulary terms, domain-specific tokenization

### Example Usage

```
@retrieval-specialist I need to design a hybrid retriever 
that combines vector + BM25 + lexical search. 
What fusion algorithm should I use?
```

**File**: [`.claude/agents/retrieval-specialist.md`](./agents/retrieval-specialist.md)  
**Related Skills**: [`/design-retriever-fusion`](./skills/design-retriever-fusion/SKILL.md)

---

## 2. ingestion-specialist

**Domain Expertise**: Document parsing, chunking strategies, preprocessing, embedding preparation

### Capabilities

✅ Chunking algorithm selection (fixed, semantic, recursive, domain-aware)  
✅ Chunk size optimization for different LLMs  
✅ Overlap strategy tuning  
✅ Preprocessing pipelines (cleaning, normalization, filtering)  
✅ Format-specific parsing (PDF, Markdown, HTML, tables)  
✅ Metadata extraction and preservation  

### When to Use

- **Ingestion design**: Setting up document processing pipelines
- **Optimization**: Balancing context window vs retrieval granularity
- **Format handling**: Parsing complex document structures
- **Quality assurance**: Data cleaning and validation

### Expertise Areas

- **Chunking**: Fixed-size, semantic (sentence/paragraph), recursive, domain-specific
- **Optimization**: Golden-set testing, NDCG measurement, overlap tuning
- **Parsing**: PDF tables/figures, multi-format support, metadata preservation
- **Performance**: Batch processing, streaming, memory efficiency

### Example Usage

```
@ingestion-specialist I have 1000 technical PDFs. 
Should I use fixed 512-token chunks or semantic chunking?
What overlap should I use for retrieval?
```

**File**: [`.claude/agents/ingestion-specialist.md`](./agents/ingestion-specialist.md)  
**Related Skills**: [`/optimize-chunking`](./skills/optimize-chunking/SKILL.md)

---

## 3. generation-specialist

**Domain Expertise**: LLM selection, prompt engineering, multi-model support, generation quality

### Capabilities

✅ LLM model selection (GPT-4, GPT-3.5, Claude, local models, fine-tuned)  
✅ Prompt engineering frameworks (few-shot, chain-of-thought, role-playing)  
✅ Temperature/top-p tuning for different use cases  
✅ Token estimation and budget management  
✅ Multi-model routing strategies  
✅ Quality metrics (factuality, coherence, cite-ability)  

### When to Use

- **Generator design**: Building answer generators
- **Prompt optimization**: Improving output quality
- **Cost optimization**: Selecting efficient models
- **Multi-model setup**: Routing to different LLMs based on query/context

### Expertise Areas

- **Models**: GPT-4 (reasoning), GPT-3.5 (speed), Claude (instruction-following), local (privacy)
- **Prompts**: Few-shot patterns, chain-of-thought, step-by-step reasoning
- **Quality**: Factuality scoring, hallucination reduction, citation extraction
- **Cost**: Token counting, budget estimation, fallback models

### Example Usage

```
@generation-specialist My current generator has 15% hallucination rate.
Should I switch to GPT-4? Use few-shot? Add chain-of-thought?
```

**File**: [`.claude/agents/generation-specialist.md`](./agents/generation-specialist.md)  
**Related Skills**: [`/add-generator`](./skills/add-generator/SKILL.md)

---

## 4. security-specialist

**Domain Expertise**: Security guards, PII redaction, injection prevention, policy/evidence gaps

### Capabilities

✅ Guard implementation (filters, detectors, policies)  
✅ PII pattern recognition (SSN, credit card, email, phone)  
✅ Prompt injection detection and prevention  
✅ Redaction strategies (masking, replacement, removal)  
✅ Technical-control mapping for compliance assessment (not certification)
✅ Provider-egress boundary analysis (Lot 20 shipped and mandatory for known remote providers; ADR-0016)
✅ Safety vs Security distinction (filter vs policy)  

### When to Use

- **Security layer design**: Implementing guards and policies
- **PII handling**: Building redaction pipelines
- **Compliance**: Mapping technical evidence and residual gaps for legal/security review
- **Injection prevention**: Protecting against adversarial inputs

### Expertise Areas

- **Guards**: Filter-based (simple rules), detector-based (ML models), policy-based (RBAC)
- **PII patterns**: SSN (XXX-XX-XXXX), CC (XXXX-XXXX-XXXX-XXXX), emails, phone
- **Safety**: Toxicity, prompt injection, jailbreaking patterns
- **Security**: Role-based access, tenant isolation, policy enforcement
- **Compliance**: GDPR (consent, retention), CCPA (opt-out), HIPAA (encryption)

### Example Usage

```
@security-specialist I need to redact SSNs and credit card numbers
from documents before retrieval. What's the best approach?
```

**File**: [`.claude/agents/security-specialist.md`](./agents/security-specialist.md)  
**Related Skills**: [`/add-security-guard`](./skills/add-security-guard/SKILL.md)

---

## 5. architecture-reviewer

**Domain Expertise**: Hexagonal layering, import validation, design patterns, refactoring

### Capabilities

✅ Layering compliance verification (outer layers depend inward on contracts/core; adapters never leak vendor types outward)
✅ Cross-domain import detection  
✅ Protocol implementation validation  
✅ Circular dependency detection  
✅ Test mirror verification (tests match src structure)  
✅ Refactoring guidance  

### When to Use

- **Code review**: Verifying architecture compliance
- **Design validation**: Checking new module structure
- **Refactoring**: Planning module reorganization
- **Protocol design**: Ensuring interface contracts are correct

### Expertise Areas

- **Layering**: Hexagonal model, one-directional dependencies
- **Imports**: Cross-domain blocking, adapter protocol usage
- **Protocols**: Protocol-first contracts, conformance testing
- **Patterns**: Registry pattern, manifest-driven wiring, factory methods
- **Testing**: Unit/contract/integration/e2e scope mapping

### Example Usage

```
@architecture-reviewer Does this new security module violate 
the hexagonal layering rules? Are there any cross-domain imports I missed?
```

**File**: [`.claude/agents/architecture-reviewer.md`](./agents/architecture-reviewer.md)  
**Related Skills**: [`/validate-architecture`](./skills/validate-architecture/SKILL.md)

---

## 6. test-specialist

**Domain Expertise**: Test design, coverage optimization, quality metrics, flakiness elimination

### Capabilities

✅ Test pyramid design (unit/contract/integration/e2e ratios)  
✅ Coverage targets by component type  
✅ Fixture design and test data generation  
✅ Flakiness elimination strategies  
✅ Performance/benchmark testing  
✅ Test maintainability patterns  

### When to Use

- **Test strategy**: Designing test suites for new features
- **Coverage optimization**: Improving coverage efficiently
- **Flakiness**: Debugging intermittent test failures
- **Quality**: Setting metrics and tracking improvements

### Expertise Areas

- **Pyramid**: Unit (70%), contract (15%), integration (10%), e2e (5%) targets
- **Scopes**: Unit (no dependencies), contract (Protocol conformance), integration (Qdrant), e2e (full pipeline)
- **Fixtures**: Factory patterns, setup/teardown, data builders
- **Performance**: Benchmark baselines, latency tracking, regression detection
- **Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`

### Example Usage

```
@test-specialist My retriever tests are flaky. 
Sometimes they pass, sometimes fail. What's causing this?
```

**File**: [`.claude/agents/test-specialist.md`](./agents/test-specialist.md)  
**Related Skills**: [`/prepare-evaluation`](./skills/prepare-evaluation/SKILL.md)

---

## 7. orchestration-specialist

**Domain Expertise**: Registry patterns, manifest-driven wiring, component composition, lifecycle

The current LangGraph adapter is fixed and is not an existing-application wrapper. ADR-0015
accepts that direction for planned Lots 21–22; the orchestration specialist must not implement
their contracts before Lot 20 and the focused contract ADR.

### Capabilities

✅ Registry pattern implementation  
✅ Manifest schema design  
✅ Factory method patterns  
✅ Component lifecycle management  
✅ Dependency injection strategies  
✅ Configuration validation  

### When to Use

- **Component wiring**: Registering and instantiating components
- **Manifest design**: Creating deployment configurations
- **Factory implementation**: Building component factories
- **Lifecycle**: Managing component initialization and cleanup

### Expertise Areas

- **Registry**: Type-safe component registration, lazy loading, factory methods
- **Manifests**: YAML schema, inheritance, override mechanisms
- **DI**: Constructor injection, property injection, service locator
- **Lifecycle**: Initialization, validation, shutdown, resource cleanup
- **Configuration**: Environment variables, secrets management, overrides

### Example Usage

```
@orchestration-specialist I need to wire a new BM25Retriever 
into the system using the registry pattern. How do I do it?
```

**File**: [`.claude/agents/orchestration-specialist.md`](./agents/orchestration-specialist.md)  
**Related Skills**: [`/design-retriever-fusion`](./skills/design-retriever-fusion/SKILL.md)

---

## 8. observability-expert

**Domain Expertise**: Distributed tracing, metrics, performance analysis, debugging

### Capabilities

✅ TraceStep schema and emission patterns  
✅ Metrics design (NDCG, MRR, latency, cost)  
✅ Structured logging setup  
✅ Performance profiling  
✅ Distributed debugging  
✅ Monitoring and alerting  

### When to Use

- **Observability design**: Adding tracing to new components
- **Metrics**: Designing performance metrics
- **Debugging**: Tracing component interactions
- **Performance**: Profiling and optimizing slow paths

### Expertise Areas

- **Tracing**: TraceStep schema, context propagation, span correlation
- **Metrics**: NDCG (ranking quality), MRR (first relevant), latency, cost/query
- **Logging**: Structured JSON logging, log levels, sampling
- **Performance**: Latency breakdown, profiling, optimization tactics
- **Dashboards**: Query traces, error rates, performance trends

### Example Usage

```
@observability-expert My RAG pipeline is slow. 
How do I trace which step is the bottleneck?
```

**File**: [`.claude/agents/observability-expert.md`](./agents/observability-expert.md)  
**Related Skills**: [`/parallel-feature-analysis`](./skills/parallel-feature-analysis/SKILL.md)

---

## How to Invoke Subagents

### In Chat

```
@subagent-name Your question or request here
```

**Example**:
```
@retrieval-specialist I'm building a hybrid retriever that combines vector 
and BM25 search. What fusion algorithm should I use?
```

### In Code Comments

```python
# @retrieval-specialist TODO: Optimize this BM25 retrieval
# Current latency: 500ms, target: <100ms
```

### Via Slash Commands

```
/invoke-subagent retrieval-specialist "Design BM25 indexing strategy"
```

---

## Subagent + Skill Mapping

Each subagent has associated **Skills** (reusable workflows):

| Subagent | Associated Skills | Files |
|----------|------------------|-------|
| **retrieval-specialist** | `/design-retriever-fusion` | [design-retriever-fusion.md](./skills/design-retriever-fusion/SKILL.md) |
| **ingestion-specialist** | `/optimize-chunking` | [optimize-chunking.md](./skills/optimize-chunking/SKILL.md) |
| **generation-specialist** | `/add-generator` | [add-generator.md](./skills/add-generator/SKILL.md) |
| **security-specialist** | `/add-security-guard` | [add-security-guard.md](./skills/add-security-guard/SKILL.md) |
| **architecture-reviewer** | `/validate-architecture` | [validate-architecture.md](./skills/validate-architecture/SKILL.md) |
| **test-specialist** | `/prepare-evaluation` | [prepare-evaluation.md](./skills/prepare-evaluation/SKILL.md) |
| **orchestration-specialist** | `/design-retriever-fusion` | [design-retriever-fusion.md](./skills/design-retriever-fusion/SKILL.md) |
| **observability-expert** | `/parallel-feature-analysis` | [parallel-feature-analysis.md](./skills/parallel-feature-analysis/SKILL.md) |

---

## Parallelization via Subagents

Run multiple subagents in **parallel** using the `/parallel-feature-analysis` skill:

```python
# Analyze retrieval + generation + security in parallel
await asyncio.gather(
    invoke_subagent("retrieval-specialist", retrieval_task),
    invoke_subagent("generation-specialist", generation_task),
    invoke_subagent("security-specialist", security_task)
)
```

**Benefits**:
- ⚡ 3 hours serial work → 1 hour parallel
- 🔍 All domains analyzed simultaneously
- 📊 Results aggregated automatically
- 🔄 Regressions detected easily

**See**: [claude-code-parallelization-orchestration.md](../docs/guides/claude-code-parallelization-orchestration.md)

---

## Integration with RAG Framework

All subagents are aligned with **V1 RAG architecture**:

```
┌─────────────────────────────────────────────────┐
│           Orchestration (orchestration-specialist) │
├─────────────────────────────────────────────────┤
│  Ingestion    Retrieval    Generation  Security  │
│ (ingestion-   (retrieval-  (generation-(security-│
│  specialist)  specialist)  specialist)specialist)│
├─────────────────────────────────────────────────┤
│    Evaluation    Observability      Architecture  │
│   (test-spec)  (observability-ex)  (architect-rev)│
├─────────────────────────────────────────────────┤
│          Core Contracts & Protocols              │
│        (architecture-reviewer scope)             │
└─────────────────────────────────────────────────┘
```

**Layering Rules** (enforced by architecture-reviewer):
- ✅ `retrieval` can use `contracts/retrieval.py`
- ✅ `generation` can use `contracts/generation.py`
- ❌ `retrieval` cannot import `generation` directly
- ✅ All use `core/models/` and `core/exceptions/`

---

## Research Papers Integration

Each subagent is grounded in **research papers** from the `.claude/research-papers/` directory:

| Subagent | Paper Categories |
|----------|------------------|
| retrieval-specialist | retrieval/, overviews/, rag_optimisation_evaluation/ |
| ingestion-specialist | chunking_strategies/, overviews/ |
| generation-specialist | generation/, advanced_architecture/ |
| security-specialist | security/ |
| architecture-reviewer | advanced_architecture/, agentic/ |
| test-specialist | rag_optimisation_evaluation/ |
| orchestration-specialist | agentic/ |
| observability-expert | rag_optimisation_evaluation/ |

---

## Best Practices

### 1. Right Subagent for the Task

```
❌ WRONG: Ask retrieval-specialist about prompt engineering
✅ RIGHT: Ask generation-specialist about prompt engineering
```

### 2. Be Specific

```
❌ VAGUE: "How do I improve retrieval?"
✅ SPECIFIC: "I have 500ms latency in hybrid retrieval. 
              BM25 is 30ms, vector is 400ms. How do I optimize vector?"
```

### 3. Include Context

```
❌ NO CONTEXT: "Should I use semantic chunking?"
✅ WITH CONTEXT: "I have 10K short customer emails (avg 500 words each). 
                  Should I use fixed 512-token or semantic chunking?"
```

### 4. Leverage Skills

```
❌ MANUAL: "Help me design a retriever fusion algorithm from scratch"
✅ SKILL: Use `/design-retriever-fusion` skill for 6-step workflow
```

---

## Troubleshooting

### Q: Subagent gives generic advice?
**A**: Be more specific about your use case, constraints, and current approach.

### Q: Which subagent should I use?
**A**: Check the "When to Use" section in each subagent's description above.

### Q: Can I invoke multiple subagents?
**A**: Yes! Use `/parallel-feature-analysis` skill to run them in parallel.

### Q: How are subagents different from slash commands?
**A**: Subagents are domain experts with deep knowledge; commands are workflows.

---

## Next Steps

### For Developers
1. **Start simple**: Use `/add-retriever` or `/add-generator` skills
2. **Leverage expertise**: Invoke specific subagents for complex problems
3. **Track progress**: Use `/parallel-feature-analysis` for benchmarking

### For Architects
1. **Review design**: Ask @architecture-reviewer for compliance checks
2. **Optimize performance**: Consult @observability-expert for tracing
3. **Plan components**: Coordinate with @orchestration-specialist

### For QA/Testing
1. **Design test suites**: Work with @test-specialist
2. **Prepare evaluation**: Use `/prepare-evaluation` skill
3. **Measure quality**: Track metrics via @observability-expert

---

## References

- [Subagent Implementations](./agents/) — All 8 subagent definitions
- [Reusable Skills](./skills/) — 19 workflow skills (add-retriever, add-generator, add-security-guard, etc.)
- [Parallelization Guide](../docs/guides/claude-code-parallelization-orchestration.md)
- [CLAUDE.md](../CLAUDE.md) — Project rules and roadmap
- [.claude/settings.json](./settings.json) — Configuration

---

**Questions?** Refer to [docs/guides/](../docs/guides/) for comprehensive guides, or invoke the appropriate subagent above.
