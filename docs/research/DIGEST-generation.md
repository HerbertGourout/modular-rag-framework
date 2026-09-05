# Research Digest — Generation, Grounding & Faithfulness

> **Auto-distilled** from the 3 arXiv PDFs formerly tracked under `.claude/research-papers/generation/`
> on **2026-07-12** (untracked 2026-09-06 — 128MB, unresolved per-paper redistribution rights, see
> `docs/refactoring/lot-16b-supply-chain.md`; the arXiv ids remain in `EVIDENCE-CATALOGUE.md`).
> Purpose: give literature backing (or corrections) to the V1 generation design
> decisions that are currently unsourced — the grounding system prompt, `temperature=0.1`, the
> numbered-source context format, the token-overlap groundedness score, and the citation builder.
>
> All three papers are **surveys**, so they cite techniques rather than run head-to-head ablations.
> Concrete numbers below are the surveyed authors' claims; **verify against the source PDFs before
> quoting**. File/function names should be re-checked before acting on any recommendation.

Files in scope:
- [`generation/synthesizers/openai_gen.py`](../../src/modular_rag/generation/synthesizers/openai_gen.py),
  [`anthropic_gen.py`](../../src/modular_rag/generation/synthesizers/anthropic_gen.py) — grounding
  prompt ("answer using ONLY the provided context"), `temperature=0.1`, context format `[i] Source: …`
- [`generation/validators/groundedness.py`](../../src/modular_rag/generation/validators/groundedness.py)
  — token-overlap score, `min_overlap_ratio=0.05`
- [`generation/citations/builder.py`](../../src/modular_rag/generation/citations/builder.py) — one
  citation per retrieved chunk, `content[:300]` passages

---

## [2404.10981] The Survey of Retrieval-Augmented Text Generation in LLMs (Huang & Huang)

Thesis: RAG spans four phases (pre-retrieval, retrieval, post-retrieval, generation); the generation
phase and its *evaluation* are where faithfulness is won or lost. **This is the most directly relevant
paper for our design.**
Actionable:
- **Generation = "Enhance with Query"**: the dominant simple pattern is to *concatenate the query with
  retrieved documents into a single input sequence* (In-Context RALM, RETRO). Our prepend-context
  approach is the textbook baseline. (§6.1)
- **Faithfulness is a statement-support ratio, not token overlap.** RAGAS defines
  `Faithfulness = Supported Statements / Total Statements`, `Context Relevance = Extracted Sentences /
  Total Sentences`, `Answer Relevance = avg cosine similarity` — all **LLM-judged / semantic**, not
  lexical. ARES improves RAGAS with a classifier + confidence intervals. (§7, Table 1)
- **Lexical overlap exists but only as a context *filter*, never as a faithfulness metric.** FILCO uses
  three sentence-level strategies — String Inclusion (STRINC), **Lexical Overlap**, and Conditional
  Cross-Mutual Information (CXMI). So token overlap is a legitimate *cheap signal*, but the survey
  positions it below semantic/statement-level checks. (§5 filtering)
- **Rejection Rate / Negative Rejection** (decline to answer when no relevant context) is a first-class
  responsible-generation metric — directly supports our "answer ONLY from context" instruction. (§7.1)
- Standard generation metrics: EM, F1 (correctness); BLEU, ROUGE-L (fluency/overlap); BERTScore/BEM
  (semantic). Limitation: surveys text-only, offers no single "best" prompt or temperature.

## [2507.09477] Towards Agentic RAG with Deep Reasoning: A Survey of RAG-Reasoning Systems

Thesis: plain RAG "may still generate unfaithful content without reasoning"; grounding is enforced by
adding verification/reasoning at generation time, not by the retrieval step alone.
Actionable (§3.3 "Generation Enhancement" — two sub-strategies):
- **Context-Aware Synthesis (§3.3.1)**: prompt the model to *rely on external context over
  memorization* (RARE adds domain knowledge to the prompt to promote context-reliance) and to prune/
  re-weight noisy context. This is the literature analogue of our "use ONLY the provided context" line.
- **Grounded Generation Control (§3.3.2)** — three named mechanisms, in rising cost order:
  1. **Fact verification** — Self-RAG's reflection markers trigger self-critique/correction during
     decoding.
  2. **Citation generation** — **RARR inserts citations while preserving stylistic coherence**;
     directly backs our citation builder as a *credibility/traceability* mechanism.
  3. **Faithful reasoning** — TRACE builds evidence-chain knowledge graphs; AlignRAG uses critique
     alignment. (V2+ scope for us.)
- Limitation: survey is oriented to *agentic/multi-step* reasoning (V2+); the grounding-control taxonomy
  is the transferable V1 takeaway. No prompt text or temperature guidance.

## [2506.10408] Reasoning RAG via System 1 or System 2: Survey for Industry Challenges

Thesis: static single-pass RAG (System 1 / predefined) works for well-formed factoid queries but
"naively concatenating retrieved passages can lead to fragmented" answers on multi-document tasks;
industry needs adaptive (System 2 / agentic) reasoning.
Actionable:
- **Prompt-based grounding is the lightweight, no-training default** — instruction-following +
  Thought/Action/Observation (ReAct) "mitigates hallucination and error propagation" vs. pure CoT by
  forcing the model to incorporate external evidence. Confirms prompt-level grounding is a valid V1
  choice before any fine-tuning. (§4.1)
- **"Lost-in-the-middle"**: long/verbose/contradictory context receives less attention; mitigate with
  *precise retrieval* + a distill/refine step (Search-o1's "Reason-in-Documents" compresses retrieved
  content before generation). Relevant to our 300-char passage truncation and chunk count. (§4.1)
- Explicitly frames our single-pass generator as **"predefined reasoning / System 1"** — correct and
  sufficient for V1 factoid QA; agentic reasoning is the deliberate V2+ upgrade path.
- Limitation: no metric formulas, no citation-format or temperature guidance.

---

## Implications for this framework (V1)

Verdict summary: our **grounding-prompt style** and **prepend/numbered-context format** are *supported*;
our **citation-per-chunk** approach is *supported*; our **token-overlap groundedness metric** is
*partially contradicted* (usable as a cheap gate, but not the faithfulness measure the literature
endorses); **`temperature=0.1`** is *not addressed* by any paper (no source sets a temperature).

1. **[P0] Keep the "answer using ONLY the provided context" instruction — it is well-supported.**
   Context-reliance prompting (RARE, [2507.09477] §3.3.1) and prompt-based grounding ([2506.10408] §4.1)
   both endorse instructing the model to prefer retrieved evidence over parametric memory. No change
   needed to [`openai_gen.py`](../../src/modular_rag/generation/synthesizers/openai_gen.py#L14).

2. **[P0] Do NOT treat token-overlap as "groundedness/faithfulness" — rename and/or demote it.**
   [2404.10981] §7 defines faithfulness as *supported-statements / total-statements* (LLM/semantic
   judged, RAGAS/ARES); lexical overlap appears only as a context *filter* (FILCO), never as the
   faithfulness metric. Recommendation: keep
   [`groundedness.py`](../../src/modular_rag/generation/validators/groundedness.py) as a cheap
   *lexical-support gate* (rename accordingly), and schedule a RAGAS-style statement-support check for
   the **V1.1 Evaluation-as-Contract** milestone. The `min_overlap_ratio=0.05` threshold has no
   literature basis — treat it as a heuristic to calibrate on the golden set, not a validated value.
   ([2404.10981])

3. **[P1] Keep one citation per retrieved chunk — it is supported as a traceability mechanism.**
   RARR's "insert citations while preserving stylistic coherence" ([2507.09477] §3.3.2) validates
   citation generation as first-class grounding control. Next step: measure **Citation Precision/Recall**
   (from [2404.10981] safety metrics) in V1.1 rather than just emitting citations. No change to
   [`builder.py`](../../src/modular_rag/generation/citations/builder.py) structure required. ([2507.09477], [2404.10981])

4. **[P1] The numbered `[i] Source: …` prepend format is the textbook baseline — keep it, but guard
   ordering.** [2404.10981] §6.1 shows concatenating query + numbered passages is the standard
   "Enhance-with-Query" pattern. However [2506.10408] §4.1 warns of **lost-in-the-middle**: place the
   most-relevant chunks at the head/tail, not buried in the middle of the context block in
   [`openai_gen.py`](../../src/modular_rag/generation/synthesizers/openai_gen.py#L52). ([2404.10981], [2506.10408])

5. **[P1] Add an explicit "if the context does not contain the answer, say you don't know" clause.**
   Rejection Rate / Negative Rejection is a named responsible-generation metric ([2404.10981] §7.1) and
   the natural complement to "answer ONLY from context." Low-cost hallucination reduction for V1.

6. **[P2] Revisit the 300-char passage truncation in the citation builder against retrieval quality,
   not a fixed length.** [2506.10408] §4.1 favours distill/refine (Search-o1 "Reason-in-Documents")
   over blunt truncation; ensure `content[:300]` doesn't sever the sentence that supports the claim.
   Consider sentence-boundary-aware truncation. ([2506.10408])

7. **[P2] `temperature=0.1` is unsourced — document it as a low-variance heuristic, not a cited value.**
   No paper in this corpus specifies a decoding temperature. Low temperature is consistent with the
   "faithful, deterministic, context-grounded" goal but should be justified in-code as an engineering
   default and, ideally, swept during V1.1 evaluation. ([2404.10981], [2507.09477], [2506.10408])

8. **[Defer — V2+] Verification-based grounding (Self-RAG reflection, TRACE evidence graphs, AlignRAG
   critique, ReAct Thought/Action/Observation).** These are the surveys' strongest faithfulness gains
   but are multi-step/agentic — explicitly V2+ per [CLAUDE.md block 01](../../CLAUDE.md). Our single-pass
   generator is correctly scoped as "System 1 / predefined reasoning" for V1. ([2507.09477], [2506.10408])
