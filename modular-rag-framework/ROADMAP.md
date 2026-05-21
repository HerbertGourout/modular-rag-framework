# Roadmap

## V1 — Core RAG `[In design]`

- [x] Architectural skeleton (contracts, models, orchestration, manifests)
- [ ] Document parsers: PDF, Word, HTML, Markdown, plain text
- [ ] Chunkers: fixed-size, adaptive (section-aware)
- [ ] Hybrid retrieval: vector (Qdrant) + BM25 fusion (RRF)
- [ ] Cross-encoder reranker
- [ ] Generators: OpenAI, Anthropic
- [ ] Basic security guard (injection detection, length check, redaction)
- [ ] Evaluation: exact match F1, recall@k, MRR
- [ ] REST API (FastAPI) + CLI (`mrag ask`, `mrag ingest`)
- [ ] Example: `examples/simple_qa/` end-to-end running
- [ ] Example: `examples/hybrid_search/`
- [ ] `pip install modular-rag[v1]` installs and works

## V2 — Agentic + Security `[Planned]`

- [ ] Adaptive query router (LLM-only / simple / agentic / graph)
- [ ] Multi-agent runtime: coordinator, planner, retriever agent, extractor, synthesizer, validator
- [ ] Multi-step agentic workflow with plan → retrieve → synthesize → critique → refine
- [ ] Agent plan inspection by security guard
- [ ] Example: `examples/agentic_rag/`

## V3 — Graph Memory `[Planned]`

- [ ] Knowledge graph construction from corpus (spaCy entity extraction)
- [ ] GraphRAG retrieval (sub-graph selection, multi-hop)
- [ ] Community detection (Louvain) + hierarchical summaries
- [ ] Reasoning graph memory (reusable per query type)
- [ ] EvoRAG: edge reinforcement/weakening from user feedback
- [ ] Neo4j adapter for `adapters/graphstores/`
- [ ] Example: `examples/graph_memory/`

## V4 — Governance `[Planned]`

- [ ] Policy-as-code: YAML rules, PolicyEngine, OPA integration
- [ ] Multi-tenant context (per-tenant knowledge base + policies)
- [ ] Multi-environment manifests (dev/staging/prod)
- [ ] Audit trail: structured logs per query, per agent action, per source access
- [ ] Human-in-the-loop: review queue for high-risk answers
- [ ] Risk profile per pipeline
- [ ] Example: `examples/secure_rag/` extended

## V5 — Multimodal `[Planned]`

- [ ] Multimodal parsers: image extraction (pymupdf), table extraction, audio transcription (Whisper), video segmentation
- [ ] Multi-vector Qdrant index (text + image + table)
- [ ] MG²-RAG: multi-granularity cross-modal graph
- [ ] Modality-specialised agents: text_agent, vision_agent, table_agent, video_agent
- [ ] VLM generation (Claude vision, GPT-4V)
- [ ] Enriched citations: image references, timecodes
- [ ] Example: multimodal QA on PDF reports with charts

---

## Milestones

| Version | Target criteria |
|---|---|
| v0.1 | `examples/simple_qa/` runs end-to-end with a real LLM |
| v0.2 | `pip install modular-rag[v1]` + all V1 checklist done |
| v1.0 | V1 + evaluation benchmark, API, CLI, full docs |
| v2.0 | V2 agentic + adaptive routing working |
| v3.0 | GraphRAG + Neo4j adapter |
| v4.0 | Policy engine + multi-tenant |
| v5.0 | Multimodal ingestion + agents |
