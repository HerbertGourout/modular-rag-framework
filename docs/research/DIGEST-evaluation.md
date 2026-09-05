# Research Digest — RAG Optimisation & Evaluation

> **Auto-distilled** from the 9 arXiv PDFs formerly tracked under
> `.claude/research-papers/rag_optimisation_evaluation/` on **2026-07-12** (untracked 2026-09-06 —
> 128MB, unresolved per-paper redistribution rights, see `docs/refactoring/lot-16b-supply-chain.md`;
> the arXiv ids remain in `EVIDENCE-CATALOGUE.md`). Purpose: make the state of the art directly usable for (a) tuning V1 hybrid
> retrieval (weighted RRF in [`src/modular_rag/retrieval/fusion/rrf.py`](../../src/modular_rag/retrieval/fusion/rrf.py),
> weights in [`manifests/presets/local-hybrid-rag.yaml`](../../manifests/presets/local-hybrid-rag.yaml)) and
> (b) designing the **V1.1 Evaluation-as-Contract** milestone (`eval/` — see [ROADMAP.md](../../ROADMAP.md)).
>
> Papers are the source of concepts; specific parameter choices below are our recommendations, not
> exact reproductions. Verify current file/function names before acting on any recommendation.

---

## [2504.14891] RAG Evaluation in the Era of LLMs: A Comprehensive Survey

Thesis: RAG must be evaluated as a hybrid system — separately at the *retrieval* and *generation*
components, then holistically — spanning IR, NLG, and LLM-as-judge metrics.
Actionable (this is the reference spec for V1.1 `eval/metrics/`):
- **IR / retriever metrics** — `Recall@k = |RD ∩ Top-k| / |RD|`; `Precision@k = TP/(TP+FP)`;
  `MRR = (1/|Q|) Σ 1/rank_i` (rank of *first* relevant doc); `NDCG@k = DCG@k / IDCG@k` with
  `DCG@k = Σ_{i=1..k} (2^rel_i − 1)/log2(i+1)`; `MAP` = mean of per-query average precision.
- **Generation metrics** — three pairwise targets: **Relevance** (response↔query),
  **Faithfulness** (response↔retrieved docs), **Correctness** (response↔gold). Surface: EM
  (normalise: lowercase, strip punctuation/articles), ROUGE-N/L, BLEU, METEOR. Semantic: BERTScore
  (P/R/F1 on contextual embeddings).
- **LLM-as-judge** — RAGAS (cosine sim on LLM embeddings for answer relevance), ARES (classifier +
  LLM embeddings for faithfulness), TRACe (Utilisation, Relevance, Adherence, Completeness). Judge
  prompts are explicit, e.g. *"Check if the response is supported by the retrieved context."*
- **Safety metrics** — Hallucination Rate, Citation Precision/Recall, Attack Success Rate (ASR).
Limitation: no single unified paradigm; LLM-judge metrics trade interpretability for robustness.

## [2604.20763] Coverage, Not Averages: Semantic Stratification for Trustworthy Retrieval Eval

Thesis: aggregate retrieval scores (mean nDCG@10) are biased because heuristic query sets
under-cover parts of the corpus; evaluation should be a *stratified* statistical estimate.
Actionable (shapes V1.1 golden-set construction):
- Cluster the corpus into entity-based semantic strata; report per-stratum nDCG@10 / Recall@k /
  MRR@k, not just the corpus-wide mean. Estimator: `μ̂_k = E[φ(q) | q ∈ S_k]` weighted by strata mass.
- Empirical finding (NFCorpus/BEIR): **26 clusters = 17.3% of the corpus but only 1.1% of queries** —
  systematic blind spots invisible to averages.
- Practice: audit each golden set for empty strata (`ŵ_k = 0` while `w_k > 0`) and synthesise queries
  to fill them before trusting a regression baseline.
Limitation: needs a clustering pass over the corpus; demonstrated on BEIR-style benchmarks only.

## [2512.16236] The Evolution of Reranking Models: From Heuristic Methods to LLMs

Thesis: a reranking stage over initial candidates is the highest-leverage quality lever in modern
RAG pipelines; cross-encoders dominate accuracy, distillation makes them affordable.
Actionable:
- **Two-stage pattern**: cheap recall (BM25 / dense) → cross-encoder rerank of top candidates,
  then keep a *small* k (paper notes `k=5` for rerank vs `k=1000` for first-stage recall).
- Cross-encoders (BERT/monoT5, MS MARCO-trained) jointly encode query-doc pairs for token-level
  interaction — best accuracy, highest latency. **ColBERT-style late interaction (MaxSim)** allows
  document pre-computation, cutting latency while keeping most accuracy.
- **Knowledge distillation** (LLM teacher → small cross-encoder student, e.g. Rank1) gives
  reasoning-aware reranking within tight latency budgets — the deployable option.
Limitation: survey reports relative gains, not absolute deltas; cross-encoder latency still the bottleneck.

## [2604.08920] Beyond Relevance: Utility-Centric Retrieval in the LLM Era

Thesis: retrieval should optimise *utility* (does the doc help the generator produce a correct
answer?) not just topical *relevance*, because docs now feed an LLM, not a human.
Actionable:
- Add a **utility signal** distinct from similarity score: LLM-agnostic vs LLM-specific, and
  context-independent vs context-dependent utility. A doc can be topically relevant yet low-utility
  (redundant/distracting) — rerank/prune on utility.
- For V1.1, correlate retriever ranking against downstream answer correctness (utility) as a metric,
  not just nDCG against relevance labels.
Limitation: position/tutorial paper (4pp), conceptual framework — no benchmark numbers or reference impl.

## [2505.01146] Retrieval-Augmented Generation in Biomedicine: A Survey

Thesis: high-stakes RAG needs hybrid sparse+dense retrieval plus reranking; a "trilemma" trades
reasoning depth vs latency vs privacy.
Actionable (validates our hybrid + RRF design):
- **Fuse BM25 with dense vectors** — consistently improves generalisation and closes the *lexical
  gap* where exact nomenclature (drug names, codes like ICD-10 `E11.9`) fails semantic match. BM25
  remains a competitive, essential hybrid component, not a legacy baseline.
- Reference systems (CliniqIR, MEDRAG) fuse signals with **Reciprocal Rank Fusion (RRF)**; DRAGON-AI
  uses **MMR** to trade relevance vs diversity. Cross-encoder rerank filters keyword-matching distractors.
- Reranking utility = **delta in nDCG@k before vs after the reranker** — a concrete regression metric.
Limitation: domain-specific (biomedical); no head-to-head fusion-weight numbers.

## [2504.10147] A Survey of Personalization: From RAG to Agent

Thesis: personalization can be injected at all three RAG stages — pre-retrieval, retrieval,
generation — plus agentic stages (understanding, planning, execution).
Actionable: pre-retrieval **query rewriting/expansion** (personalized or auxiliary) is a low-cost
lever that improves recall before fusion — relevant to a future ingestion/query-processing step.
Standard eval metrics reused (ROUGE/BLEU for generation, IR metrics for retrieval); tracks datasets
and metrics per subtask.
Limitation: personalization/agent focus is **V2+ scope** here — defer; only the query-processing idea
touches V1.

## [2604.19779] ESGLens: An LLM-Based RAG Framework for ESG Report Analysis

Thesis: a domain RAG PoC combining GRI-standard-guided extraction, source-traceable QA, and
embedding-regression scoring on ~300 reports.
Actionable (patterns, not metrics for us):
- **Typed chunking** — segment heterogeneous PDFs into typed chunks (text / tables / charts) before
  embedding; relevant to ingestion parsers.
- **Traceability audit** — 8/10 extracted claims verified against source; enforce citation/provenance
  as a first-class output (aligns with V1.2 audit trail and generation citation builders).
- Best config: ChatGPT embeddings + NN regressor, **Pearson r ≈ 0.48, R² ≈ 0.23** (modest signal).
Limitation: PoC, small dataset, single ESG pillar; scoring signal weak.

## [2604.19820] KnowPilot: A Knowledge-Driven Copilot for Domain Tasks

Thesis: domain agents fail from missing domain knowledge; inject task priors + explicit knowledge +
experiential (memory) knowledge, supporting private/local deployment.
Actionable: separate **explicit knowledge** (retrieved from structured repos) from **experiential
knowledge** (captured via human-AI interaction memory) — a memory-module design note for V2/V3.
Evaluated on domain writing via quality scores (accuracy, professional style, logical rigor).
Limitation: agentic + memory system = **V2+/V3 scope**; not V1-actionable.

## [2507.21117] Harnessing LLMs to Overcome Recommender System Challenges

Thesis: LLMs unify the classic candidate-generation → ranking → reranking recommender pipeline via
language-native prompt-driven retrieval and RAG.
Actionable: reinforces the **multi-stage retrieve→rank→rerank** architecture and the accuracy vs
scalability vs real-time trade-off; RAG used for cold-start / long-tail via external knowledge.
Limitation: recommender-systems domain, largely orthogonal to our QA RAG — lowest direct relevance.

---

## Implications for this framework (V1 / V1.1)

Prioritized, mapped to real files/milestones. Verify names before editing.

1. **[P0] Implement the IR metric quartet exactly per [2504.14891] in `eval/metrics/retriever_metrics.py`** —
   NDCG@k (`(2^rel−1)/log2(i+1)`), MRR (first-relevant rank), Recall@k, MAP. These are the V1.1
   contract metrics named in [ROADMAP.md](../../ROADMAP.md). ([2504.14891], [2505.01146])
2. **[P0] Define generator metrics as the 3 pairwise targets** — Relevance (↔query), Faithfulness
   (↔retrieved docs), Correctness (↔gold) — in `eval/metrics/generator_metrics.py`. Map our planned
   `factuality.py` → Faithfulness (RAGAS/ARES/TRACe style), `semantic_similarity.py` → BERTScore /
   embedding cosine. ([2504.14891])
3. **[P0] Report reranker gain as Δ nDCG@k (pre vs post rerank), evaluated at small k (~5)** —
   bake this into `regression_detector.py`; it is a direct, cheap regression signal. ([2505.01146], [2512.16236])
4. **[P1] Keep BM25 in the hybrid fusion — it is load-bearing, not legacy.** Validates current
   [`hybrid.py`](../../src/modular_rag/retrieval/retrievers/hybrid.py) + RRF; BM25 closes the lexical
   gap for exact tokens (codes, names) that dense retrieval misses. ([2505.01146])
5. **[P1] Stratify golden sets by semantic cluster, not just count** — build
   `eval/golden_sets/{finance,healthcare,manufacturing,default}.yaml` with per-stratum coverage checks
   and report per-stratum nDCG@10, so the "F1 > 0.85 / >90% coverage" criteria are unbiased. ([2604.20763])
6. **[P1] Tune weighted RRF, not just uniform weights.** [`rrf.py`](../../src/modular_rag/retrieval/fusion/rrf.py)
   already supports `weights` and `rrf_k=60` (standard). Sweep dense-vs-BM25 weights against the
   stratified golden set (P5) and set them in
   [`local-hybrid-rag.yaml`](../../manifests/presets/local-hybrid-rag.yaml); keep `rrf_k=60` unless a
   sweep says otherwise. ([2505.01146], [2604.20763])
7. **[P2] Add a utility-aware evaluation axis** — correlate retriever ranking with downstream answer
   correctness (utility), complementing relevance-labeled nDCG, in `eval/metrics/system_metrics.py`.
   ([2604.08920])
8. **[P2] Consider distilled cross-encoder / ColBERT-style reranking** for the reranker slot — late
   interaction (MaxSim, pre-computable) or an LLM-distilled student keeps latency within budget while
   raising precision. Wire via registry, keep k small. ([2512.16236])
9. **[P2] Enforce citation/provenance as a first-class generation output** — feeds V1.2 audit trail;
   measure Citation Precision/Recall. ([2604.19779], [2504.14891])
10. **[Defer — V2+] Personalization, agent memory, recommender patterns** ([2504.10147], [2604.19820],
    [2507.21117]) are out of V1 scope per [CLAUDE.md block 01](../../CLAUDE.md). Only pre-retrieval
    query rewriting is a candidate V1 ingestion enhancement.
