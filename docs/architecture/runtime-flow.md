# Runtime Flow Diagrams

This document shows how data moves through the pipeline at runtime for each version of the framework. Each diagram focuses on a specific architectural concern. Read `data-model.md` for details on the objects passed between stages.

---

## V1 — Simple RAG (query path)

The V1 query path is a linear pipeline: guard → retrieve → rerank → generate → guard. The `Trace` object is threaded through every step and accumulates latency and token counts so the final `Answer` can be debugged end-to-end.

The two most important things to notice in this diagram:
1. The security guard runs **twice** — before retrieval (to block injections) and after generation (to catch PII leakage in the answer).
2. `Telemetry.record_trace()` fires after the answer is validated, not before — so the trace is complete when it is persisted.

```mermaid
sequenceDiagram
    participant U as User
    participant E as RAGEngine
    participant G as SecurityGuard
    participant R as Retriever
    participant RR as Reranker
    participant LLM as Generator
    participant T as Telemetry

    U->>E: answer("question")
    E->>G: check_query(query)
    G-->>E: GuardResult(allowed=True)
    E->>R: retrieve(query, k=20)
    R-->>E: [RetrievedChunk × 20]
    E->>RR: rerank(query, chunks, k=5)
    RR-->>E: [RetrievedChunk × 5]
    E->>LLM: generate(query, context, trace)
    LLM-->>E: Answer(text, citations)
    E->>G: check_answer(answer)
    E->>T: record_trace(trace)
    E-->>U: Answer
```

---

## V1 — Ingestion path

When a file is ingested, it follows a transformation chain before landing in the vector and BM25 indices. This diagram shows that chain. The embedding step is the only one that calls an external service (OpenAI or HuggingFace); all other steps are local.

The output of `ingest_path()` is a list of `Chunk` objects. The engine then embeds and indexes them. The number of chunks written to the store is returned to the caller.

```mermaid
sequenceDiagram
    participant U as User / CLI
    participant E as RAGEngine
    participant IP as ingest_path()
    participant P as Parser
    participant N as Normalizer
    participant En as MetadataEnricher
    participant C as Chunker
    participant Emb as Embedder
    participant Idx as Indexer

    U->>E: ingest(path, chunker)
    E->>IP: ingest_path(path, chunker)
    IP->>P: parse(path) → Document
    IP->>N: normalize(doc) → Document
    IP->>En: enrich(doc) → Document
    IP->>C: chunk(doc) → list[Chunk]
    IP-->>E: list[Chunk]
    E->>Emb: embed([c.content for c in chunks]) → list[list[float]]
    Note over E: writes embedding into each Chunk in-place
    E->>Idx: index(chunks) → int
    E-->>U: n_indexed
```

---

## V1 — Data lifecycle (Document → Answer)

This flowchart shows the full transformation from raw file to final answer. It is the same path as the sequence diagrams above but displayed as a data-flow graph, making it easier to see which stores are involved and where data branches.

```mermaid
flowchart LR
    File[File on disk] -->|parse| Doc[Document\nfrozen]
    Doc -->|normalize + enrich| DocE[Document\nenriched]
    DocE -->|chunk| Chunks[list Chunk\nembedding=None]
    Chunks -->|embed| ChunksV[list Chunk\nwith embedding]
    ChunksV -->|index| Store[(Qdrant\n+ BM25)]

    Query[Query\nfrozen] -->|check_query| Guard{SecurityGuard}
    Guard -->|allowed| Ret[Retriever.retrieve]
    Guard -->|blocked| Err[SecurityError]
    Store --> Ret
    Ret -->|RRF fusion| RC[list RetrievedChunk]
    RC -->|rerank| RCR[list RetrievedChunk\nreranked]
    RCR -->|generate| Gen[Generator]
    Gen -->|check_answer + redact| FinalAns[Answer\n+ Citations + trace_id]
```

---

## V2 — Agentic RAG

> **Historical design reference, not current behavior.** The components this section names
> (`Router`, `Coordinator`, `Planner`, `Retriever Agent`, `Extractor`, `Synthesizer`,
> `Validator`) were removed in Lot 17 (`docs/refactoring-plan.md`): the router was constructed
> by `RAGEngine` but its classification output was never actually read anywhere, and the five
> agent classes had zero consumers anywhere in the codebase. Per
> [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) §5.2, generic multi-agent
> orchestration is delegated to the selected external engine (LangGraph,
> [ADR-0006](../adr/0006-external-engine-selection.md)) via the `DocumentEngine` port
> (`contracts/engine.py`) — reached through `adapters/llms/langgraph_engine.py`'s
> `LangGraphEngineAdapter`, not through the diagram below. Kept as a record of the original
> design intent, not a description of anything the framework does today.

The V2 router was meant to classify each query and dispatch it to the right execution path.
Simple queries would go directly to the V1 pipeline; complex queries requiring multi-step
reasoning would go to the Coordinator, which spun up a team of specialised agents. The Validator
could loop back to the Retriever Agent if groundedness was too low — the self-correction loop
this design intended for agentic RAG.

```mermaid
flowchart TD
    Q[Query] --> Router
    Router -->|llm_only| LLM[Generator]
    Router -->|simple_rag| V1[V1 Pipeline]
    Router -->|agentic_rag| Coord[Coordinator]

    Coord --> Planner
    Planner -->|ExecutionPlan| Coord
    Coord --> RetAgent[Retriever Agent]
    RetAgent --> Extractor
    Extractor --> Synthesizer
    Synthesizer --> Validator
    Validator -->|low groundedness| RetAgent
    Validator -->|ok| Output[Generator → Answer]
```

---

## V3 — Graph RAG

> **Historical design reference, not current behavior.** Per ADR-0005 §5.2, GraphRAG traversal
> and multi-hop reasoning are delegated to the selected external engine, not built as the native
> pipeline diagrammed below. A native `KnowledgeGraph` data model does exist
> (`memory/graph/knowledge_graph.py`) and is retained with a documented caveat — see its own
> docstring and `docs/refactoring/lot-17-prototype-retirement.md` — but it is not wired into any
> retriever or pipeline today, and the Entity Extractor/Graph Retriever/Context Builder
> components below were never built.

In V3's original design, retrieval would start from the knowledge graph rather than the vector
store. The Entity Extractor would identify named entities in the query; the Graph Retriever
would expand them to a local sub-graph; the Vector Retriever would enrich with additional chunk
context. The Context Builder would merge both and feed the Generator — intended to enable
multi-hop reasoning (A → B → C) with explicit proof paths in the answer.

```mermaid
flowchart LR
    Q[Query] --> EE[Entity Extractor]
    EE --> GR[Graph Retriever]
    GR --> SubG[Sub-graph + community summaries]
    SubG --> VR[Vector Retriever]
    VR --> Merge[Context Builder]
    Merge --> LLM[Generator]
    LLM --> Ans[Answer + proof path]
```
