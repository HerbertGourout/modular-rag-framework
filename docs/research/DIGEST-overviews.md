# RAG Survey Digest — Overviews

> **Auto-distilled** from the 5 arXiv PDFs formerly tracked under `.claude/research-papers/overviews/`
> on **2026-07-12** (untracked 2026-09-06 — 128MB, unresolved per-paper redistribution rights, see
> `docs/refactoring/lot-16b-supply-chain.md`; the arXiv ids remain in `EVIDENCE-CATALOGUE.md`).
> Purpose: extract cross-cutting, state-of-the-art guidance for this framework's V1 pipeline
> (ingestion → hybrid retrieval → reranking → generation → guards, with `TraceStep` throughout)
> and its V1→V5 [ROADMAP.md](../../ROADMAP.md). Numbers are quoted from the source papers.
> This is a reading aid, not a spec — verify against current code before acting.

---

## [2405.06211] A Survey on RAG Meeting LLMs (Fan et al., KDD 2024)

**Thesis:** Systematizes retrieval-augmented LLMs across three axes — architecture, training, application — as the antidote to hallucination and stale parametric knowledge.

- **Retriever taxonomy:** sparse (BM25/TF-IDF, no training, keyword-only) vs dense (DPR bi-encoder; Contriever one-encoder). Contriever *without* fine-tuning ≈ BM25; both are beaten by DPR *fine-tuned on target data* — fine-tuning matters more than dense-vs-sparse.
- **Granularity:** chunk/passage is the mainstream unit (compact, low redundancy); token-level (kNN-LM) suits rare/OOD patterns; entity-level suits entity-centric tasks.
- **Pre-retrieval enhancement:** query rewrite (Rewrite-Retrieve-Read), expansion (Query2doc), HyDE (hypothetical doc embedding), query augmentation — all lift both sparse and dense recall.
- **Post-retrieval enhancement:** rerank (R2G Retrieve-Rerank-Generate), compress (RECOMP → summary before prepend), filter (BlendFilter). Warning: noisy/irrelevant retrieved docs can *harm* generation.
- **Augmentation integration** happens at input-, intermediate-, or output-layer stages.
- **Motivating stat:** legal-domain hallucination rates of 69–88% for SOTA LLMs without retrieval.
- **Limitations:** iterative retrieve↔generate loops degrade when either side is low-quality; input-length limits force compression.

## [2410.12837] A Comprehensive Survey of RAG: Evolution & Future Directions (Gupta, Ranjan, Singh)

**Thesis:** Traces RAG from DrQA/REALM/Lewis-2020 to today, arguing factually-grounded generation requires tight retrieval-generation coupling plus richer metadata.

- **BM25 remains a strong baseline**; DPR bi-encoder adds semantics; **cross-encoder rerankers** jointly encode query+doc for context-aware relevance at higher compute cost.
- **RAPTOR** (hierarchical recursive embed→cluster→summarize tree) retrieves at multiple abstraction levels; **+20% on QuALITY** with GPT-4.
- **RAFT** trains the model to ignore distractor docs and cite relevant sources with chain-of-thought; **FILCO** filters context to curb over/under-reliance.
- **Self-RAG** reflection tokens for adaptive retrieval; **Self-Route** dynamically routes a query to RAG *or* long-context LLM to balance cost vs performance.
- **Metadata-centric** workflow: prepare→rewrite→retrieve→read with a "Meta-Knowledge Summary" per doc cluster beats naive retrieve-then-read.
- **Explicit recommendation:** combine dense + sparse (hybrid) retrieval.
- **Limitations/challenges:** scalability & compute cost, retrieval relevance, bias amplification from sources, retrieval-generation coherence, black-box interpretability.

## [2506.00054] RAG: Architectures, Enhancements, and Robustness Frontiers (Sharma, 2025)

**Thesis:** Organizes RAG into retriever-centric / generator-centric / hybrid / robustness-oriented designs and quantifies each enhancement's measured gains and trade-offs.

- **Reranking is essential**, not optional: RankRAG **+7.8% MRR@10**, uRAG **+8% MRR@10**; adaptive list truncation (RLT) cuts noise **15%**.
- **Fusion:** RAG-Fusion (multiple reformulated queries + **reciprocal rank fusion**) **+9% accuracy** — validates this repo's RRF choice.
- **Filtering:** FILCO **+8.6 EM, up to 64% hallucination reduction**; SEER **+13.5% F1 with 9.25× context reduction**; IB filtering **+3.2 EM at 2.5% compression**.
- **Adaptive retrieval** (TA-ARE) cuts redundant retrievals **14.9%**; DRAGIN triggers at token level via entropy.
- **Efficiency:** speculative pipelining cuts time-to-first-token **20–50%**; RAGCache reuses KV tensors across retrievals.
- **Graph/hybrid:** GraphRAG multi-hop recall **+6.4 pts**; KRAGEN hallucination **−20–30%**; LinkedIn KG deployment **+77.6% retrieval MRR, −28.6% resolution time**.
- **Security (critical):** **BadRAG** — poisoning just **0.04% of corpus → 98.2% attack success, 74.6% system failure**; TrojanRAG hides embedding-level backdoors that survive sanitization.
- **Seven recurrent operational failure points** exist (retrieval errors, context-consolidation failures, hallucinations, incomplete answers) — argues for unified observability.
- **Core finding:** retrieval alone is insufficient; the strongest systems couple retrieval + generation + **verification** in iterative loops. Key trade-offs: precision↔flexibility, efficiency↔faithfulness, modularity↔coordination.

## [2507.13334] A Survey of Context Engineering for LLMs (Mei et al., 2025)

**Thesis:** Reframes prompt design as "Context Engineering" — a formal optimization over an assembly function `C = A(c_instr, c_know, c_tools, c_mem, c_state, c_query)` — synthesizing 1400+ papers.

- **Modular / Agentic / Graph-Enhanced RAG** are the three maturity tiers (GraphRAG, LightRAG, HippoRAG, RAPTOR, Self-RAG, Modular RAG); agentic RAG treats retrieval as a dynamic, planned operation.
- **Retrieval as information-theoretic optimum:** select `c_know` maximizing mutual information `I(Y*; c_know | c_query)` — "maximally informative," not merely "semantically similar."
- **Long-context cost is real:** self-attention is O(n²); Mistral-7B 4K→128K tokens = **122× compute** — motivates compression/filtering over dumping everything into the prompt.
- **Self-refinement** (Self-Refine, Reflexion, N-CRITICS) and structured reasoning (CoT/ToT/GoT) let generation recover from imperfect retrieval; GoT **+62% quality, −31% cost** vs ToT.
- **Evaluation** must be both component-level and system-level; emerging pain points: attribution, self-validation dependencies, context-handling failures.
- **Critical gap:** models comprehend rich context far better than they *generate* sophisticated long-form output.

## [2510.04905] Retrieval-Augmented Code Generation, Repository-Level (Tao, Qin, Liu, 2026)

**Thesis:** For repository-scale tasks, shallow file/text retrieval fails; RACG needs structure-aware retrieval to hold long-range dependencies and global consistency (domain-specific but its retrieval lessons generalize).

- **Retrieval modalities:** identifier match, sparse (BM25/TF-IDF), dense (CodeBERT/UniXcoder), **graph-based** (AST / call-graph / dependency-graph), and **hybrid** (lexical + embedding + structural) for balanced precision/recall.
- **Hybrid BM25 + dense** is the recurring baseline (ReACC, CEDAR, RAP-Gen); **RepoCoder** popularized **iterative multi-round retrieval** refining context each round.
- **Structure-aware chunking (cAST):** recursively partition the AST and merge nodes into semantically coherent, information-dense units — preserves structure vs blind fixed-size splitting.
- **Static-analysis integration** (STALL+, Monitor-Guided Decoding) and **De-Hallucinator** (retrieve project-specific API refs) cut hallucination by grounding in the actual corpus.
- **Limitations:** retrieval noise, graph-construction/maintenance overhead, scalability, and **privacy-preserving retrieval** — proprietary code/data cannot leave premises (a governance concern).

---

## Implications for this framework

Prioritized, mapped to real modules and roadmap items. Verify each path/flag against current code before acting.

1. **Keep hybrid + RRF; make reranking first-class (V1.0).** Multiple surveys confirm dense+sparse fusion and reciprocal rank fusion as SOTA-competitive (RAG-Fusion +9% [2506.00054]; hybrid baseline [2410.12837][2510.04905]). This validates [`retrieval/retrievers/hybrid.py`](../../src/modular_rag/retrieval/retrievers/hybrid.py) + [`retrieval/fusion/rrf.py`](../../src/modular_rag/retrieval/fusion/rrf.py). Ensure the cross-encoder rerank stage (`reranker_k`) is always in the default preset — reranking gave +7.8% MRR@10 [2506.00054].

2. **Add a post-retrieval context-filter stage before generation (V1.0/V1.1).** FILCO-style filtering yielded +8.6 EM and up to 64% hallucination reduction; SEER cut context 9.25× [2506.00054]. Noisy docs actively harm generation [2405.06211]. Implement as a `retrieval/` post-processor or `generation/` pre-step (respect hexagonal rules — no cross-domain import).

3. **Instrument the "seven failure points" in TraceStep (V1.0 — observability).** [2506.00054] enumerates recurrent operational failures (retrieval errors, context-consolidation failures, hallucinations, incomplete answers). Each retrieval/rerank/filter/generate `TraceStep` should emit score distributions, retained-vs-dropped counts, and a sufficient-context signal so these are diagnosable — this is exactly the mandatory `Trace.add_step()` discipline in [.claude/.instructions.md §3](../../.claude/.instructions.md).

4. **Treat corpus poisoning as a real threat in the security layer (V1.2 audit).** BadRAG showed 0.04% corpus poisoning → 98.2% attack success [2506.00054]; RACG raises privacy-preserving retrieval [2510.04905]. Feed this into `security/audit/` data-lineage (source→processing→response) and integrity validation — reinforces the V1.2 Compliance Audit Trail and ADR-0003 governance direction.

5. **Upgrade chunking from fixed-size toward structure-aware + hierarchical (V1.0/V1.1).** cAST AST-aware chunking [2510.04905] and RAPTOR hierarchical summary trees (+20% QuALITY) [2410.12837] both beat blind splitting. Extend [`ingestion/chunkers/`](../../src/modular_rag/ingestion/chunkers/) with a structure-respecting chunker; use the `optimize-chunking` skill to measure the delta.

6. **Ground evaluation metrics in what the surveys actually report (V1.1).** Golden-set metrics should be MRR@10 / nDCG@10 / EM / F1 / FactScore — the exact metrics quoted across [2506.00054][2410.12837]. Align `eval/metrics/` and `eval/golden_sets/` accordingly; retrieval-alone is insufficient, so include a faithfulness/groundedness metric [2506.00054].

7. **Scope agentic patterns (Self-RAG, CRAG, adaptive retrieval) to V2, not V1.** Reflection-token / corrective / iterative-verification loops give the biggest robustness gains [2506.00054][2507.13334] but require agent orchestration — correctly deferred to V2.0 per [ROADMAP.md](../../ROADMAP.md). Note them as the V2 target now.

8. **Design the V3 cost optimizer around measured levers.** Self-Route (route to RAG vs long-context LLM) [2410.12837], TA-ARE adaptive retrieval (−14.9% redundant calls), RAGCache KV reuse, and speculative pipelining (−20–50% TTFT) [2506.00054] are the concrete mechanisms behind V3.1's `orchestration/cost_optimizer/` and `query_cache.py`. Long-context is expensive (122× compute 4K→128K) [2507.13334] — retrieval+filter stays cost-competitive.

9. **Adopt "maximally informative, not merely similar" as the retrieval north star.** The information-theoretic framing `max I(Y*; c_know | c_query)` [2507.13334] argues for utility/relevance-aware selection (SEER, IB filtering) over raw cosine similarity — a design principle for future rerankers and fusion weighting.

10. **Note the comprehension-vs-generation gap for generation quality work.** LLMs understand rich context better than they generate long-form output [2507.13334]; pair retrieval improvements with generation-side faithfulness controls (citations, groundedness checks in `generation/`) rather than assuming better retrieval alone fixes answer quality.
