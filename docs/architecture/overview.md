# Architecture Overview — Modular RAG Framework

> This document is the technical specification (cahier technique) for the framework.

---

## 1. Purpose

This framework provides a **context OS** for RAG and agentic systems: a control plane over knowledge, orchestration, memory, governance, and multimodality. It is built around three pillars:

1. **Declarative orchestration** — pipelines are described in YAML (manifests), not in imperative Python.
2. **Composable retrieval** — chunking, embedding, indexing, fusion, and reranking are swappable contracts.
3. **Verifiable agentic reasoning** — several specialized agents replace the single monolithic LLM call.

---

## 2. Guiding principles

| Principle | Implication |
|---|---|
| **Strict modularity** | Every major capability is a contract (`typing.Protocol`) |
| **Loose coupling** | The orchestrator depends on interfaces, never on concrete implementations |
| **Native evaluation** | Every building block has an associated measurement protocol (`contracts/evaluation.py`) |
| **Secure by default** | Input filtering and guardrails run upstream of reasoning |
| **Native observability** | Traces, provenance, scores, costs, and latency logged at every step |
| **Progressive rollout** | Advanced features (graph, governance, multimodal) stay optional until stabilized |

---

## 3. The system's six planes

```
┌─────────────────────────────────────────────────────────────┐
│  CONTROL PLANE          manifests, policies, routing        │
├─────────────────────────────────────────────────────────────┤
│  INGESTION PLANE        parsing, chunking, enrichment       │
├────────────────────────┬────────────────────────────────────┤
│  KNOWLEDGE PLANE       │  REASONING PLANE                   │
│  vector/lex/graph      │  planning, agents, generation      │
│  store, reranking      │                                    │
├────────────────────────┴────────────────────────────────────┤
│  SAFETY PLANE           detectors, filters, redaction       │
├─────────────────────────────────────────────────────────────┤
│  EVALUATION PLANE       benchmarks, scorers, dashboards     │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Roadmap V1 → V5

Cette section décrit l'état **cible** de chaque version — ce qu'elle est censée permettre
une fois terminée, indépendamment de ce qui est déjà livré aujourd'hui. Pour l'état réel
(quelles cases sont cochées), voir [ROADMAP.md](../../ROADMAP.md) ; pour la même
progression racontée sans jargon technique, voir [docs/onboarding.md](../onboarding.md),
section 3. Les cinq versions ne sont pas des lots indépendants — chacune s'appuie sur le
pipeline construit par la précédente plutôt que de le remplacer.

### V1 — Core RAG
**What the framework enables:**
- Source ingestion (files, folders) with parsing (PDF, Word, HTML, Markdown, plain text).
- Optimized chunking (fixed-size, section-adaptive).
- Hybrid dense + lexical search (vector + BM25) with RRF fusion.
- Cross-encoder reranking.
- Grounded generation (citations, groundedness) via OpenAI or Anthropic.
- Basic security: query filtering, injection detection, PII redaction.
- Native evaluation: exact match, recall@k, MRR.
- Exposure via HTTP API (FastAPI) and CLI (`mrag ask`, `mrag ingest`).
- Reproducible configuration through versioned YAML manifests.

### V2 — Agentic + Adaptive
**Additions:**
- Adaptive routing: LLM-only / simple RAG / agentic RAG / graph RAG depending on complexity.
- Multi-agent runtime: coordinator, planner, retriever agent, extractor, synthesizer, validator.
- Multi-step workflows (plan → retrieve → synthesize → critique → refine).
- Multi-step security: inspection of agent plans.
- Agentic execution traces (which agent, which tool, how long).

### V3 — Graph Memory
**Additions:**
- Knowledge graph extraction from the corpus (entities, relations, communities).
- GraphRAG: graph querying + contextual subgraph injected into the LLM.
- Explicit multi-hop reasoning (A → B → C with evidence).
- Hierarchical per-community summaries (Louvain).
- Reasoning graphs as reusable memory.
- EvoRAG: edge reinforcement / weakening driven by feedback.

### V4 — Governance
**Additions:**
- Policy-as-code: YAML rules versioned in Git, enforced at runtime.
- Multi-tenant: separate context domains (finance, HR, legal…).
- Multi-environment: dev / staging / prod with progressively stricter policies.
- Full audit: who accessed what, when, with which result.
- Human-in-the-loop: human validation for sensitive answers.
- Per-pipeline risk profiles.

### V5 — Multimodal
**Additions:**
- Multimodal ingestion: text, PDFs with images and tables, audio, video.
- Multi-vector index: text + image (CLIP/Colpali) + tables + video segments.
- MG²-RAG: multi-granularity cross-modal graph.
- Modality-specialized agents: text_agent, vision_agent, table_agent, video_agent.
- Enriched answers: video timecodes, image references, table excerpts.

---

## 5. V1 execution flow (simple RAG)

```
Query
  │
  ▼
SecurityGuard.check_query()          ← safety plane
  │
  ▼
Retriever.retrieve()                 ← knowledge plane
  │
  ▼
Reranker.rerank()                    ← knowledge plane
  │
  ▼
Generator.generate()                 ← reasoning plane
  │
  ▼
SecurityGuard.check_answer()         ← safety plane
  │
  ▼
Telemetry.record_trace()             ← control plane
  │
  ▼
Answer (text + citations + trace_id)
```

---

## 6. Founding contracts

The contracts in `src/modular_rag/contracts/` are the framework's immutable core. Every implementation — internal or external — must satisfy these Protocols:

| Contract | Role | V |
|---|---|---|
| `Chunker` | `chunk(doc) → [Chunk]` | V1 |
| `Embedder` | `embed(texts) → [[float]]` | V1 |
| `Indexer` | `index(chunks)` / `delete(ids)` | V1 |
| `Retriever` | `retrieve(query, k) → [RetrievedChunk]` | V1 |
| `Reranker` | `rerank(query, chunks, k) → [RetrievedChunk]` | V1 |
| `Generator` | `generate(query, context, trace) → Answer` | V1 |
| `SecurityGuard` | `check_query(query)` / `check_answer(answer)` | V1 |
| `Evaluator` | `evaluate(query, answer, expected, context)` | V1 |
| `Planner` | `plan(query) → ExecutionPlan` | V2 |
| `Agent` | `run(task) → AgentResult` | V2 |
| `Telemetry` | `record_trace(trace)` | V1 |
| `Storage` | `put/get/delete/exists` | V1 |
| `Redactor` | `redact(text) → str` | V1 |
| `ManifestLoader` | `load(path) → PipelineManifest` | V1 |

---

## 7. Architecture decisions

See the ADRs in `docs/adr/`:
- [ADR-0001](../adr/0001-modular-architecture.md) — Six planes, contracts/implementations separation
- [ADR-0002](../adr/0002-contracts-and-plugins.md) — Protocols + Factory Registry
- [ADR-0003](../adr/0003-security-and-governance.md) — Safety vs Security, policy-as-code

---

## 8. Data models

The domain models are defined in `src/modular_rag/core/models/`. They are Pydantic v2 objects — no ORM, no database. See `data-model.md` for the full documentation.

| Model | File | Frozen | Usage |
|---|---|---|---|
| `Document` | `document.py` | ✓ | Ingestion unit: source, raw content, metadata |
| `Chunk` | `chunk.py` | ✗ | Sub-segment of a Document, with optional embedding |
| `Query` | `query.py` | ✓ | User query + routing hint |
| `RetrievedChunk` | `retrieved.py` | ✓ | Chunk + score + rank + retrieval method |
| `Citation` | `answer.py` | ✗ | Pointer from an answer to a source chunk |
| `Answer` | `answer.py` | ✗ | Generated text + citations + trace_id |
| `TraceStep` | `trace.py` | ✗ | Latency + tokens for one pipeline step |
| `Trace` | `trace.py` | ✗ | Full audit of an execution (accumulated via `add_step()`) |
| `PolicyRule` | `policy.py` | ✗ | Condition + action (allow/deny/redact/warn) |
| `Policy` | `policy.py` | ✗ | Set of rules scoped to a tenant |
| `Metrics` | `metrics.py` | ✗ | Evaluation scores (recall@k, MRR, groundedness…) |

**Key invariants:**
- `Document` and `Query` are immutable (`frozen=True`). Any modification produces a new instance.
- `Chunk.token_estimate` is a computed property (`len(content.split())`), not stored.
- `Trace.add_step()` is the only way to add a step — it atomically updates the `total_latency_ms`, `total_input_tokens`, and `total_output_tokens` totals.
- `Policy.sorted_rules()` returns the rules sorted by decreasing priority.
- `Metrics.summary()` returns only the non-None fields.

---

## 9. Manifest → pipeline wiring

The complete path from a YAML file to an operational pipeline:

```
manifests/presets/local-hybrid-rag.yaml
  │
  ▼ app/bootstrap.py → load_manifest(path) → PipelineManifest
  │
  ▼ orchestration/registry.py → ComponentRegistry.default()
  │   # _default_factories maps "fixed" → FixedSizeChunker, "bm25" → BM25Retriever, etc.
  │
  ▼ registry.wire(manifest) → Container
  │   # Reads manifest.chunker.type, manifest.retriever.type …
  │   # Calls factory(config) for each component
  │   # Stores wired instances in Container.components dict
  │
  ▼ app/container.py → Container (holds all wired instances)
  │
  ▼ orchestration/engine.py → RAGEngine(container)
  │   # engine.ingest() / engine.answer() use container.get(Chunker), etc.
  │
  ▼ cli/main.py or api/routes.py → calls engine methods
```

To wire a new component:
1. Implement the corresponding contract in `contracts/`.
2. Add the factory in `orchestration/registry.py → _default_factories`.
3. Reference the type in the manifest YAML: `chunker: {type: my_chunker, ...}`.

---

## 10. Ingestion pipeline (V1 detail)

```
File (PDF / Markdown / plain text)
  │
  ▼ ingestion/parsers/
  │   TextParser → Document  (for .txt, .md, .html)
  │   PDFParser  → Document  (for .pdf, via PyMuPDF)
  │
  ▼ ingestion/normalizers/TextNormalizer.normalize(doc)
  │   • Collapse excessive newlines (3+ → 2)
  │   • Collapse excessive spaces (2+ → 1)
  │   • Strip leading/trailing whitespace
  │   → new Document (frozen → new instance)
  │
  ▼ ingestion/enrichers/MetadataEnricher.enrich(doc)
  │   • Computes word_count, lang, reading_level
  │   • Merges with existing metadata
  │   → new Document
  │
  ▼ contracts/chunking.Chunker.chunk(doc) → list[Chunk]
  │   FixedSizeChunker  : windows of N tokens with overlap
  │   AdaptiveChunker   : splits on Markdown headings (##, ###)
  │
  ▼ Embedder.embed([c.content for c in chunks]) → list[list[float]]
  │   → writes the embedding into each Chunk in place
  │
  ▼ Indexer.index(chunks) → int
      QdrantStore : upserts as PointStruct (vector + payload)
      BM25Retriever : rebuilds the BM25 index over the corpus
```

Note: Embedding and indexing happen in `RAGEngine.ingest()`, not in `ingest_path()`. The separation is intentional — `ingest_path()` is testable without any external service.

---

## 11. Hybrid retrieval algorithm (RRF)

Hybrid retrieval combines two ranked result lists (dense vector + lexical BM25) into a single fused list via **Reciprocal Rank Fusion**:

```
RRF_score(d) = Σᵢ  1 / (rrf_k + rankᵢ(d))

  where:
    rrf_k  = 60  (smoothing constant, standard in the literature)
    rankᵢ  = rank of document d in list i (1-based)
    Σ      = sum over all result lists (vector, BM25)
```

Example with 2 lists:
```
document "Q4 revenue"
  rank_vector = 3  → 1 / (60 + 3) = 0.0159
  rank_bm25   = 1  → 1 / (60 + 1) = 0.0164
  RRF_score   = 0.0159 + 0.0164 = 0.0323
```

The vector/BM25 ratio in the `local-hybrid-rag.yaml` preset is **0.7 / 0.3**: vector results carry more weight because they capture semantics, while BM25 boosts exact matches on technical terms.

After fusion, chunks are re-ranked by decreasing `RRF_score`. A cross-encoder reranker then refines this ranking over the top-k (default: 5).

---

## 12. Error hierarchy

All framework exceptions inherit from `ModularRAGError` (defined in `core/errors.py`). The complete tree:

```
ModularRAGError                     ← base of all framework errors
├── ConfigurationError              ← invalid manifest or settings
│   └── ManifestError               ← YAML cannot be loaded or validated
├── RegistryError                   ← component not found in the registry
├── IngestionError                  ← parsing or chunking failed
├── IndexingError                   ← write to the vector/lexical store failed
├── RetrievalError                  ← retrieval operation failed
├── GenerationError                 ← LLM call failed or response unusable
├── SecurityError                   ← guard blocks a query or an answer
│   └── PolicyViolationError        ← pipeline action violates a declared policy
├── EvaluationError                 ← scoring or benchmark failed
├── GraphError                      ← graph construction or traversal failed (V3)
├── AgentError                      ← agent task failed (V2)
└── StorageError                    ← storage backend operation failed
```

**Handling rule:** catch the most specific exception possible. Only catch `ModularRAGError` at the HTTP/CLI handler level to return a generic error response. Never silently swallow a `SecurityError` — it must always be logged.
