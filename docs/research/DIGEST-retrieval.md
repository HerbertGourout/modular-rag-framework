# Retrieval Strategies — Research Digest

**Auto-distilled** from the 3 arXiv PDFs in [`.claude/research-papers/retrieval/`](../../.claude/research-papers/retrieval/), plus one paper cross-cited from `security/` (2603.21654 — see [EVIDENCE-CATALOGUE.md](EVIDENCE-CATALOGUE.md) for the provenance note), on **2026-07-12**.
Purpose: provide literature backing (or corrections) for the currently-unsourced V1 retrieval defaults in
[`fusion/rrf.py`](../../src/modular_rag/retrieval/fusion/rrf.py) (weighted RRF, `rrf_k=60`),
[`retrievers/hybrid.py`](../../src/modular_rag/retrieval/retrievers/hybrid.py) (`vector_weight=0.7`/`bm25_weight=0.3`, `k*2` over-fetch),
[`rerankers/cross_encoder.py`](../../src/modular_rag/retrieval/rerankers/cross_encoder.py) (`ms-marco-MiniLM-L-6-v2`, `reranker_k=5`),
and [`manifests/presets/local-hybrid-rag.yaml`](../../manifests/presets/local-hybrid-rag.yaml) (`k=20`, `reranker_k=5`).
Numbers are quoted from the papers; **verify against the source PDF** before treating any figure as ground truth.

> Corpus caveat: none of these 4 papers is a hybrid-fusion tuning study. Two are surveys (security, GraphRAG),
> one is an inference-efficiency method, one is a domain-specific dense-retriever training method. They speak to
> retrieval *patterns* (over-fetch→filter, two-stage rerank, hard-negative training) more than to specific constants.

---

## [2405.16178] Accelerating Inference of RAG via Sparse Context Selection (Sparse RAG)

**Thesis:** Encode retrieved documents in parallel, then let the LLM self-assess each one via a control token
and decode against only the high-scoring subset — combining relevance filtering and generation into one pass.

**Actionable techniques (with numbers):**
- Over-fetch then filter: retrieves **20 contexts**, keeps on average **7.84** (PopQA, short-form) / **4.45** (QMSum, long-form).
- Filtering to a small set **improves quality**, not just latency: F1 71.16 vs dense RAG 69.99 (PopQA) while using ~8/20 contexts.
- Confidence-threshold sweep (Table 4): quality rises then plateaus/drops as more contexts are dropped
  (PopQA F1 peaks ~0.15 threshold → 7.84 kept; over-filtering at 0.30 drops F1 to 68.2). There is a sweet spot, not "fewer is always better".
- An "internal" per-context assessor beat CRAG's external T5-XXL classifier — a cheaper single-model reranking signal can match a dedicated reranker.

**Limitations:** Requires LoRA fine-tuning + a Per-Context-Assessment training task (not a drop-in for our off-the-shelf
cross-encoder). Evaluated on PopQA/QMSum only, Gemini-family models, on-device latency focus.

---

## [2606.01482] Beyond Topical Similarity: Contrastive Evidence Retrieval (CERA)

**Thesis:** Fine-tune a dense retriever with subjectivity-based *hard-negative* selection plus an attention-alignment
loss so it retrieves genuinely *evidential* passages, not merely topically-similar ones.

**Actionable techniques (with numbers):**
- Hard-negative mining that distinguishes neutral/supportive/contradictory passages beats treating all non-relevant docs as equal.
- Gains over Contriever baseline: **Recall@1 +0.077, Recall@3 +0.107, Recall@5 +0.131** on clinical-trial corpus.
- Attention-alignment (KL over CLS-to-token) improves faithfulness (Sufficiency 0.2073 → 0.0939) at competitive retrieval quality.
- Reinforces that **Recall@5** is a standard operating cutoff — consistent with our `reranker_k=5` final depth.

**Limitations:** Requires retriever fine-tuning + human-annotated evidence rationales (POS-weighted); single clinical
domain (Evidence Inference 2.0). Says nothing about fusion weights, RRF, or cross-encoder choice; it improves the
*dense* leg, not the fusion layer.

---

## [2603.21654] Towards Secure RAG: A Comprehensive Review of Threats, Defenses and Benchmarks

**Thesis:** Survey (152 papers, cs.CR) mapping the full RAG pipeline's attack surface — data poisoning, adversarial
attacks, membership inference — and the input/output-side defenses against them.

**Actionable techniques (with numbers):**
- **Adversarial pre-filtering** of retrieved passages is listed as a core input-side defense: a small amount of
  poisoned text in the knowledge base can flip outputs, so the retrieval stage is a security boundary, not just a quality one.
- Consolidates benchmarks/standards for evaluating retrieval robustness (no fusion-tuning figures).

**Limitations:** Out of the retrieval-tuning domain — offers no numbers for fusion weights, `rrf_k`, over-fetch, or
reranker depth. Relevance here is to `security/` (V1.2 audit / guards), not to `retrieval/fusion`. Included for completeness.

---

## [2501.13958] A Survey of Graph Retrieval-Augmented Generation (GraphRAG)

**Thesis:** Survey positioning graph-structured retrieval (knowledge-based / index-based / hybrid) as the fix for
flat top-k RAG's failures on multi-hop, distributed-knowledge, professional-domain queries.

**Actionable techniques (with numbers):**
- Explicitly endorses **two-stage retrieval (retrieve → re-rank)** "for higher recall and precision" as a mature
  naive-RAG improvement — general support for our over-fetch-wide + rerank-to-small-`k` pipeline.
- Endorses **adaptive retrieval** that "dynamically adjusts retrieval strategies based on query types" — a routing
  direction beyond static fusion weights.
- Notes retrieval quality *declines as the knowledge base grows*, motivating a reranking second stage at scale.

**Limitations:** GraphRAG is **V3 scope** per [ROADMAP](../../ROADMAP.md) — do not implement here. Survey gives
directional patterns only; no concrete fusion weights, `rrf_k`, or cross-encoder numbers.

---

## Implications for this framework (V1)

Prioritized, mapped to the four files. **Verdict up front:** the corpus does **not directly address** any of our
specific constants — `rrf_k=60`, `0.7/0.3` weights, and `ms-marco-MiniLM` are **not validated and not contradicted**
by these 4 papers. What *is* supported is the *shape* of the pipeline (over-fetch → rerank → small final `k`).

1. **Over-fetch → rerank → small final `k` is well-supported.** Sparse RAG [2405.16178] retrieves 20 and keeps
   ~4–8 with *higher* quality; GraphRAG [2501.13958] endorses two-stage retrieve→rerank for recall+precision.
   Our `k=20` (manifest) → `reranker_k=5` ([`hybrid.py`](../../src/modular_rag/retrieval/retrievers/hybrid.py#L26)) sits squarely in this validated range. **Keep.**

2. **`k*2` over-fetch before fusion is directionally right but under-aggressive.** Sparse RAG [2405.16178] fetches
   20 and keeps ~5 (a ~4x fetch:keep ratio). Our [`hybrid.py`](../../src/modular_rag/retrieval/retrievers/hybrid.py#L39) fetches `k*2=40` per leg then reranks to 5 — that is generous
   fetch relative to final depth, so `k*2` is safe; not addressed as an exact constant. **Keep; treat 2x as a floor, not a ceiling.**

3. **`reranker_k=5` matches standard practice.** CERA [2606.01482] reports Recall@5 as a primary cutoff; Sparse RAG's
   kept-context averages (4.45–7.84) bracket 5. `reranker_k=5` in [manifest](../../manifests/presets/local-hybrid-rag.yaml#L30) is **supported**. **Keep.**

4. **Don't over-filter.** Sparse RAG [2405.16178] Table 4 shows quality *drops* when filtering is too aggressive
   (F1 68.2 at threshold 0.30). If `reranker_k` is ever lowered below ~4, expect recall loss — make it a manifest-tunable, not a hardcoded floor.

5. **`vector_weight=0.7 / bm25_weight=0.3`: UNSOURCED by this corpus.** No paper here tunes dense-vs-lexical fusion weights.
   Treat the 0.7/0.3 split in [`hybrid.py`](../../src/modular_rag/retrieval/retrievers/hybrid.py#L20-L21) as a reasonable-but-unvalidated prior; flag for empirical tuning on our own golden set (V1.1 eval), not literature.

6. **`rrf_k=60`: UNSOURCED by this corpus.** The `_RRF_K = 60` constant in [`rrf.py`](../../src/modular_rag/retrieval/fusion/rrf.py#L5) traces to the original
   Cormack et al. 2009 RRF paper, which is **not in this corpus**. Nothing here contradicts it; keep the `# standard RRF constant`
   comment but cite the real source (Cormack 2009) rather than implying these papers back it.

7. **`ms-marco-MiniLM-L-6-v2` reranker: NOT ADDRESSED.** No paper here benchmarks cross-encoder rerankers. Sparse RAG
   [2405.16178] instead argues an *in-model* assessor can beat an external classifier — a future alternative to a standalone
   cross-encoder, but requires fine-tuning (V2+). For V1, the ms-marco default stands unchallenged. **Keep.**

8. **Bigger V1 lever is the dense leg, not the fusion constants.** CERA [2606.01482] shows hard-negative-trained
   embeddings yield Recall@5 +0.13 — far larger than any plausible gain from re-tuning `rrf_k` or the 0.7/0.3 split.
   Prioritize embedding/retriever quality (adapters/embeddings) over fusion-constant tuning.

9. **Adaptive/query-routed retrieval is a documented next step (defer to V2).** GraphRAG [2501.13958] and Sparse RAG
   both point to per-query strategy selection; our static weights are fine for V1, but note routing as a V2 `orchestration/` direction.

10. **Retrieval is a security boundary (cross-ref V1.2).** [2603.21654] flags adversarial pre-filtering of retrieved
    passages; when `security/` guards land, the retrieval output — not just the query — should pass through them.
