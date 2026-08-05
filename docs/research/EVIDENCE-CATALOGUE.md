# Research Evidence Catalogue

Lot 17 (`docs/refactoring-plan.md` — "Complete Claude/documentation consolidation and a
research evidence catalogue... binary provenance is resolved"). This is the per-paper index
`docs/research/README.md`'s folder-level table doesn't provide: every PDF under
`.claude/research-papers/`, by arXiv id, with its digest status and any provenance anomaly
found while compiling this list. Built by cross-referencing the actual files on disk
(`find .claude/research-papers -iname "*.pdf"`, `md5sum` for duplicate detection) against every
`## [arXiv-id] Title` header across all seven `DIGEST-*.md` files — not by re-reading all 56
PDFs, which is out of this lot's scope (that's the specialist-agent digest-generation process
`docs/research/README.md`'s own "Regenerating a digest" section already documents).

## Binary provenance findings

- **56 files on disk, 55 unique papers.** `2604.11623v3.pdf` ("Context Kubernetes: Declarative
  Orchestration of Enterprise Knowledge for Agentic AI") is byte-identical (verified via
  `md5sum`) in both `advanced_architecture/` and `agentic/`. It is digested once, in
  `DIGEST-architecture.md`, under its `advanced_architecture/` home. Not removed in this lot —
  a stray duplicate file is not evidence of a redistribution-rights problem, and removing it
  touches the same git-history-preservation caveat as the broader 56-PDF question (Lot 16b,
  escalated, "leave as-is for now" per Herbert Gourout).
- **One cross-folder citation, not a second duplicate**: `2603.21654v1.pdf`
  ("Towards Secure RAG: A Comprehensive Review of Threats, Defenses and Benchmarks") lives only
  in `security/`, but is cited and summarized in both `DIGEST-security.md` (its home) and
  `DIGEST-retrieval.md` (legitimately relevant to retrieval-time threat awareness). This is why
  `DIGEST-retrieval.md`'s own header claims "4 arXiv PDFs" when `retrieval/` holds only 3 files
  — the 4th is this cross-citation, not a missing/misplaced file. Recorded here so the
  discrepancy reads as resolved, not as an unexplained inconsistency.
- **38 unique papers have a digest entry; 17 do not** (all in `agentic/`, `graph_rag/`, and
  `multimodal_rag/` — deferred per `docs/research/README.md`'s own "Gaps and deferred corpora"
  note: "distill at V2 start" / "V3" / "V5"). Listed below by arXiv id only, since no digest
  thesis exists yet for them.

## Digested papers (38 unique, one cross-cited in two digests)

| arXiv id | Title | Folder | Digest |
|---|---|---|---|
| 2405.16178 | Accelerating Inference of RAG via Sparse Context Selection (Sparse RAG) | `retrieval/` | [DIGEST-retrieval.md](DIGEST-retrieval.md) |
| 2606.01482 | Beyond Topical Similarity: Contrastive Evidence Retrieval (CERA) | `retrieval/` | [DIGEST-retrieval.md](DIGEST-retrieval.md) |
| 2603.21654 | Towards Secure RAG: A Comprehensive Review of Threats, Defenses and Benchmarks | `security/` (cross-cited in `retrieval/`'s digest) | [DIGEST-security.md](DIGEST-security.md), [DIGEST-retrieval.md](DIGEST-retrieval.md) |
| 2501.13958 | A Survey of Graph Retrieval-Augmented Generation (GraphRAG) | `retrieval/` | [DIGEST-retrieval.md](DIGEST-retrieval.md) |
| 2404.10981 | The Survey of Retrieval-Augmented Text Generation in LLMs (Huang & Huang) | `generation/` | [DIGEST-generation.md](DIGEST-generation.md) |
| 2507.09477 | Towards Agentic RAG with Deep Reasoning: A Survey of RAG-Reasoning Systems | `generation/` | [DIGEST-generation.md](DIGEST-generation.md) |
| 2506.10408 | Reasoning RAG via System 1 or System 2: Survey for Industry Challenges | `generation/` | [DIGEST-generation.md](DIGEST-generation.md) |
| 2601.04377 | Disco-RAG: Discourse-Aware Retrieval-Augmented Generation | `chunkings_strategies/` | [DIGEST-chunking.md](DIGEST-chunking.md) |
| 2602.22225 | SmartChunk Retrieval: Query-Aware Chunk Compression with Planning | `chunkings_strategies/` | [DIGEST-chunking.md](DIGEST-chunking.md) |
| 2603.25333 | Adaptive Chunking: Optimizing Chunking-Method Selection for RAG | `chunkings_strategies/` | [DIGEST-chunking.md](DIGEST-chunking.md) |
| 2604.04936 | W-RAC: Web Retrieval-Aware Chunking | `chunkings_strategies/` | [DIGEST-chunking.md](DIGEST-chunking.md) |
| 2604.12047 | Empirical Evaluation of PDF Parsing and Chunking for Financial QA | `chunkings_strategies/` | [DIGEST-chunking.md](DIGEST-chunking.md) |
| 2604.15583 | SAGE: Selective Attention-Guided Extraction for Token-Efficient Indexing | `chunkings_strategies/` | [DIGEST-chunking.md](DIGEST-chunking.md) |
| 2504.14891 | RAG Evaluation in the Era of LLMs: A Comprehensive Survey | `rag_optimisation_evaluation/` | [DIGEST-evaluation.md](DIGEST-evaluation.md) |
| 2604.20763 | Coverage, Not Averages: Semantic Stratification for Trustworthy Retrieval Eval | `rag_optimisation_evaluation/` | [DIGEST-evaluation.md](DIGEST-evaluation.md) |
| 2512.16236 | The Evolution of Reranking Models: From Heuristic Methods to LLMs | `rag_optimisation_evaluation/` | [DIGEST-evaluation.md](DIGEST-evaluation.md) |
| 2604.08920 | Beyond Relevance: Utility-Centric Retrieval in the LLM Era | `rag_optimisation_evaluation/` | [DIGEST-evaluation.md](DIGEST-evaluation.md) |
| 2505.01146 | Retrieval-Augmented Generation in Biomedicine: A Survey | `rag_optimisation_evaluation/` | [DIGEST-evaluation.md](DIGEST-evaluation.md) |
| 2504.10147 | A Survey of Personalization: From RAG to Agent | `rag_optimisation_evaluation/` | [DIGEST-evaluation.md](DIGEST-evaluation.md) |
| 2604.19779 | ESGLens: An LLM-Based RAG Framework for ESG Report Analysis | `rag_optimisation_evaluation/` | [DIGEST-evaluation.md](DIGEST-evaluation.md) |
| 2604.19820 | KnowPilot: A Knowledge-Driven Copilot for Domain Tasks | `rag_optimisation_evaluation/` | [DIGEST-evaluation.md](DIGEST-evaluation.md) |
| 2507.21117 | Harnessing LLMs to Overcome Recommender System Challenges | `rag_optimisation_evaluation/` | [DIGEST-evaluation.md](DIGEST-evaluation.md) |
| 2504.09593 | ControlNet: A Firewall for RAG-based LLM System | `security/` | [DIGEST-security.md](DIGEST-security.md) |
| 2505.06579 | PoisonCraft: Practical Poisoning of RAG | `security/` | [DIGEST-security.md](DIGEST-security.md) |
| 2505.08728 | Securing RAG: A Risk Assessment and Mitigation Framework | `security/` | [DIGEST-security.md](DIGEST-security.md) |
| 2508.01084 | Provably Secure RAG (SAG) | `security/` | [DIGEST-security.md](DIGEST-security.md) |
| 2511.10128 | RAGFort: Dual-Path Defense Against Knowledge-Base Extraction | `security/` | [DIGEST-security.md](DIGEST-security.md) |
| 2602.06616 | Confundo: Learning-to-Poison for Practical RAG | `security/` | [DIGEST-security.md](DIGEST-security.md) |
| 2604.12201 | AdversarialCoT: Single-Document Retrieval Poisoning for Reasoning | `security/` | [DIGEST-security.md](DIGEST-security.md) |
| 2604.20932 | Adaptive Defense Orchestration (ADO): Sentinel–Strategist | `security/` | [DIGEST-security.md](DIGEST-security.md) |
| 2405.06211 | A Survey on RAG Meeting LLMs (Fan et al., KDD 2024) | `overviews/` | [DIGEST-overviews.md](DIGEST-overviews.md) |
| 2410.12837 | A Comprehensive Survey of RAG: Evolution & Future Directions | `overviews/` | [DIGEST-overviews.md](DIGEST-overviews.md) |
| 2506.00054 | RAG: Architectures, Enhancements, and Robustness Frontiers | `overviews/` | [DIGEST-overviews.md](DIGEST-overviews.md) |
| 2507.13334 | A Survey of Context Engineering for LLMs | `overviews/` | [DIGEST-overviews.md](DIGEST-overviews.md) |
| 2510.04905 | Retrieval-Augmented Code Generation, Repository-Level | `overviews/` | [DIGEST-overviews.md](DIGEST-overviews.md) |
| 2604.11623 | Context Kubernetes: Declarative Orchestration of Enterprise Knowledge for Agentic AI | `advanced_architecture/` (byte-identical duplicate also in `agentic/`, see above) | [DIGEST-architecture.md](DIGEST-architecture.md) |
| 2604.20666 | ORPHEAS: A Cross-Lingual Greek–English Embedding Model for RAG | `advanced_architecture/` | [DIGEST-architecture.md](DIGEST-architecture.md) |
| 2604.20452 | HaS: Accelerating RAG through Homology-Aware Speculative Retrieval | `advanced_architecture/` | [DIGEST-architecture.md](DIGEST-architecture.md) |

## Not yet digested (17 unique papers — deferred per roadmap discipline)

No thesis/technique summary exists for these yet; listed by arXiv id and folder only, so the
catalogue is complete even where the digest isn't. Distilling them is explicitly deferred, not
forgotten — see `docs/research/README.md`'s "Gaps and deferred corpora": `agentic/` at V2 start,
`graph_rag/` at V3, `multimodal_rag/` at V5.

| Folder | arXiv ids |
|---|---|
| `agentic/` (4 undigested — the 5th, `2604.11623v3`, is the duplicate digested under `advanced_architecture/` above) | 2604.07595, 2604.12766, 2604.18509, 2604.20795 |
| `graph_rag/` (5) | 2604.12185, 2604.14220, 2604.15676, 2604.20844, 2604.20859 |
| `multimodal_rag/` (8) | 2603.00511, 2604.04372, 2604.04969, 2604.05418, 2604.06179, 2604.12352, 2604.15663, 2604.16313 |

## Redistribution rights (cross-reference, not re-decided here)

Per-paper arXiv redistribution rights were never individually verified for any of the 56 files
— escalated in Lot 16b (`docs/refactoring/lot-16b-supply-chain.md`) and confirmed by Herbert
Gourout as "leave as-is for now." This catalogue does not change that status; it exists so that
*if* that decision is revisited, there is a complete, accurate per-paper list to work from
instead of re-deriving one from scratch.
