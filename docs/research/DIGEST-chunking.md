# Chunking Strategies — Research Digest

**Auto-distilled** from the 6 arXiv PDFs formerly tracked under `.claude/research-papers/chunkings_strategies/`
on **2026-07-12** (untracked 2026-09-06 — 128MB, unresolved per-paper redistribution rights, see
`docs/refactoring/lot-16b-supply-chain.md`; the arXiv ids remain in `EVIDENCE-CATALOGUE.md`).
Purpose: make the state of the art directly usable when building/optimizing V1 ingestion chunkers
(`src/modular_rag/ingestion/chunkers/` — currently `fixed.py`, `adaptive.py`). Numbers are quoted from the papers;
verify against the source PDF before treating any figure as ground truth.

---

## [2601.04377] Disco-RAG: Discourse-Aware Retrieval-Augmented Generation

**Thesis:** Injecting discourse structure (intra-chunk RST trees + an inter-chunk rhetorical graph) into the
prompt/plan lets an LLM synthesize dispersed evidence, beating flat top-k RAG without fine-tuning.

**Actionable techniques (with numbers):**
- Baseline retrieval uses **chunk size 256 tokens, no sliding window, plain top-k** — their controlled default.
- Ablation: retrieval quality peaks at **chunk size 256** (score 49.33) vs larger sizes — smaller, coherent chunks win.
- Build a per-chunk discourse tree (EDU segmentation + RST relations), then classify each chunk-pair relation
  (Elaboration/Contrast/… or UNRELATED) into a rhetorical graph; compile the graph into a generation "blueprint".
- Reported gains over standard RAG: **+8.22 points** (Loong Set 1), **+12.74 LLM-Score** on Loong overall; SOTA on EM/ROUGE-L.

**Limitations:** Needs an RST parser + pairwise relation calls (extra LLM/inference cost); gains shown on long-doc
QA/summarization (Loong, ASQA, SciNews), not short factoid corpora; the discourse graph is V2+ territory, not V1 chunking.

---

## [2602.22225] SmartChunk Retrieval: Query-Aware Chunk Compression with Planning

**Thesis:** No single chunk granularity is optimal; a learned planner should pick the smallest+largest useful chunk
size *per query*, and a compression module supplies cheap coarse context alongside fine-grained chunks.

**Actionable techniques (with numbers):**
- **Query-adaptive granularity:** a planner predicts the smallest and largest chunk sizes to retrieve for each query,
  enabling multi-level retrieval instead of one fixed size.
- **Chunk Compression Encoder:** maps a cluster of fine chunks into a single compressed embedding (coarse view) so the
  system mixes raw + compressed context to cut tokens.
- Trained with multi-objective RL (accuracy vs monetary cost vs latency) via a method they call STITCH.
- Results: **~30%** accuracy gain over cheap baselines; vs SOTA tree/graph RAG, **+1.7% QA accuracy** and **+4.0% retrieval
  recall** at far lower cost; shown orthogonal/composable with other RAG methods.

**Limitations:** Requires training a planner + compressor (RL pipeline) — heavyweight vs a static chunker; benefits are
largely cost/efficiency; needs a multi-level chunk hierarchy pre-built at ingest time.

---

## [2603.25333] Adaptive Chunking: Optimizing Chunking-Method Selection for RAG

**Thesis:** Chunking should not be a fixed global choice; select the best chunking *method* per document, add two new
splitters + post-processing, and downstream RAG improves with no model/prompt changes. **Most directly relevant paper.**

**Actionable techniques (with numbers):**
- **Split-then-Merge recursive splitter:** recursively split, then merge, with target sizes **1,100 and 600 tokens**;
  beats single-pass recursive splitting.
- **Post-processing:** split oversized tables (>1000 tokens) into sub-tables; **merge fragments <100 tokens**; cap chunks
  at a **max ~1,100 tokens**, **min 100 tokens**. Post-processing alone adds a few points at negligible cost.
- **Per-document method selection** (router over token/sentence/recursive/semantic/LLM-regex splitters): "no single method
  is universally optimal."
- Results: answer **correctness 62–64% → 72%** (best config 78.01% G-Eval); **retrieval completeness +16.5–18.0%**.

**Limitations:** Method-selection router + coreference/mention-cluster steps add ingest complexity; correctness gains from
the intrinsic router beyond post-processing are modest (0.4–2.4 pts); evaluated with LLM-judge metrics (G-Eval).

---

## [2604.04936] W-RAC: Web Retrieval-Aware Chunking

**Thesis:** For high-volume web ingestion, don't send full text to an LLM to chunk it — feed only element **IDs +
hierarchy + ordering + metadata** and let the LLM emit grouping decisions, slashing token cost while staying deterministic.

**Actionable techniques (with numbers):**
- Parse HTML/DOM into elements; give the LLM **identifiers, heading depth/section hierarchy, ordering, optional token-length
  metadata** — never raw text — so it plans chunk grouping, not generation.
- Results vs traditional agentic chunking: **output tokens −84.54%** (1,467.53 → 226.82 tokens/file); chunking-related LLM
  cost cut by ~an order of magnitude; input tokens **+49.90%** (2,447.93 → 3,669.64) — net large cost/latency win, benefits KV caching.

**Limitations:** Assumes structured input (HTML/DOM element tree) — not applicable to flat PDFs/plain text without a parser
that emits element IDs; still requires an LLM call per document; input-token increase means gains depend on output-heavy chunking.

---

## [2604.12047] Empirical Evaluation of PDF Parsing and Chunking for Financial QA

**Thesis:** Systematic sweep of PDF parsers × chunkers × overlap on FinanceBench/TableQuest — gives concrete, tuned
defaults for a RAG pipeline. **Most directly actionable for parameter defaults.**

**Actionable techniques (with numbers):**
- Hard cap **512 tokens/chunk** across all strategies (token/sentence/recursive/semantic/SDPM/neural).
- **Overlap sweep (0% / 25% / 50%):** **25% overlap (128 tokens) is the sweet spot** — e.g. MRR up to 0.658 / 0.833;
  0% overlap is worst, 50% slightly *worse* than 25% while doubling index size. **Recommend 512 tokens + 25% (128-token) overlap.**
- Recursive chunker = fewest segments (cheapest index); **sentence chunking = strong low-cost fallback**.
- Retriever pairing: dense bi-encoder **E5** wins overall (P@1 0.76, R@3 0.919, MRR 0.844); parser **PyMuPDF** gives best
  page-level retrieval (MRR 0.646); pdfminer + recursive chunker best combo (MRR 0.655).

**Limitations:** Domain-specific (financial docs, tables); page-level retrieval metrics; overlap findings assume 512-token
chunks — may not transfer to very small or very large chunk sizes.

---

## [2604.15583] SAGE: Selective Attention-Guided Extraction for Token-Efficient Indexing

**Thesis:** A training-free, plug-in filter uses model attention to score text spans and keep only the highest-utility ones
under a **user-specified token budget** — cutting context ~90% with competitive accuracy.

**Actionable techniques (with numbers):**
- Split doc into fixed local chunks (sized to the local model context), score each **span by attention** to the query,
  extract top spans under an explicit **token budget**, assemble into a reduced-context prompt.
- Results: **4th on QuALITY-hard public leaderboard using only a 10% context budget → ~90% token reduction** with
  competitive accuracy; consistent wins over embedding-RAG baselines across budgets; reuses KV-cache for efficiency.

**Limitations:** Needs access to model attention (white-box/local model) — not usable with pure black-box API LLMs;
budget-constrained filtering is a retrieval/compression stage, not a pure chunker; benefits strongest on long templated docs.

---

## Implications for this framework (V1)

Prioritized, each backed by a cited paper. Applies to existing chunkers; no source code was modified.

1. **[P0] Set defaults to 512 tokens + 25% (128-token) overlap** in
   [`FixedSizeChunker`](../../src/modular_rag/ingestion/chunkers/fixed.py) and
   [`AdaptiveChunker`](../../src/modular_rag/ingestion/chunkers/adaptive.py). `2604.12047` shows 25% overlap is the empirical
   sweet spot (0% worst, 50% no better + larger index). **Current chunkers use `chunk_overlap=64` — raise toward 128 when
   `chunk_size≈512`, i.e. overlap ≈ 25% of chunk_size.** Note both chunkers count *characters*, not tokens; a token-aware
   length function is needed to honor these numbers (see #6).

2. **[P0] Add split-then-merge + min-size merging to `AdaptiveChunker`** (`2603.25333`). It already splits on headings/paragraphs
   then caps size; add a **merge pass that fuses sub-`min_chunk_size` fragments (<100 tokens)** and caps at ~1,100 tokens.
   Post-processing alone lifted retrieval completeness +16.5–18.0% and answer correctness 62–64%→72% at negligible cost.

3. **[P1] Prefer smaller, coherent chunks for long-doc/QA corpora** (`2601.04377`): retrieval peaked at **256 tokens** with no
   sliding window. Consider exposing a 256-token preset for QA-heavy pipelines alongside the 512-token financial default —
   the optimal size is corpus-dependent, so make it a manifest knob, not a hardcoded constant.

4. **[P1] Add a chunker-selection router (per-document method choice)** (`2603.25333`, `2602.22225`): "no single method is
   universally optimal." A lightweight router picking between `fixed`, `adaptive`, and a future recursive/semantic splitter,
   selected via manifest YAML + `orchestration/registry.py`, matches both papers. Keep it heuristic in V1 (RL planner is V2+).

5. **[P1] Special-case tables/oversized structured blocks** (`2603.25333`): split tables >1,000 tokens into sub-tables during
   ingest. Relevant once DOCX/HTML parsers land (`src/modular_rag/ingestion/parsers/` — `docx_parser.py`, `html_parser.py`
   are new in the working tree); pairs naturally with a table-aware chunker.

6. **[P2] Make chunk sizing token-based, not char-based.** Both current chunkers slice on `len(text)` (characters). Every
   paper reports thresholds in **tokens** (`2604.12047`, `2601.04377`, `2603.25333`). Add a pluggable token-count function
   (lazy-import the tokenizer per rule #7) so `chunk_size`/`chunk_overlap` map to the researched numbers.

7. **[P2] Sentence-boundary-aware fallback splitter** (`2604.12047`): sentence chunking is the strong low-cost fallback and
   avoids mid-sentence cuts that fixed-size slicing produces. A cheap sentence splitter is a good default when no structure exists.

8. **[P2] Structure-aware (ID/hierarchy) chunk planning for HTML** (`2604.04936`): when the new `html_parser.py` emits a DOM
   element tree, plan chunks over **element IDs + heading depth + ordering** rather than raw text — deterministic and cache-friendly.
   The LLM-driven variant is V2+ (needs `adapters/llms/`), but the ID/hierarchy grouping heuristic is V1-safe.

9. **[P3 / V2+] Query-adaptive granularity & attention/budget compression** (`2602.22225`, `2604.15583`): per-query chunk-size
   planning and attention-guided budgeted extraction are retrieval/generation-stage concerns needing a trainable planner or
   white-box attention. Record as V2+ backlog; do not implement in V1 ingestion.
