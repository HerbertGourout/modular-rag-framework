# Security Research Digest — RAG Threats & Defenses

> **Auto-distilled** from the 9 arXiv PDFs formerly tracked under `.claude/research-papers/security/`
> on **2026-07-12** (untracked 2026-09-06 — 128MB, unresolved per-paper redistribution rights, see
> `docs/refactoring/lot-16b-supply-chain.md`; the arXiv ids remain in `EVIDENCE-CATALOGUE.md`).
> Purpose: make the state of the art directly usable for hardening V1 security
> ([`security/filters/basic_guard.py`](../../src/modular_rag/security/filters/basic_guard.py),
> [`security/redaction/patterns.py`](../../src/modular_rag/security/redaction/patterns.py)) and for planning
> the **V1.2 Compliance Audit Trail** (see [ROADMAP.md](../../ROADMAP.md)).
>
> Attack classes are described defensively only — **no working exploit payloads are reproduced here.**
> Numbers are the papers' reported figures, not measurements on this framework.

---

## [2504.09593] ControlNet: A Firewall for RAG-based LLM System

- **Thesis:** An "AI firewall" controls inbound/outbound RAG query flow using internal-activation shift
  signals rather than regexes, enforcing role-based access on retrieved content.
- **Attack taxonomy (reuse this):** two risk domains — *data breaching* (reconnaissance, data exfiltration,
  unauthorized access) and *data poisoning* (knowledge poisoning, conversation hijacking) — **5 attacks total.**
- **Key finding:** unstructured NL makes pure regex matching insufficient; semantic/activation features
  needed for multi-role flows. Detector reaches **AUROC > 0.909**; mitigation costs **< 0.03 precision /
  < 0.09 recall** drop.
- **Actionable:** treat regex guard as first-line only; add role/permission checks on *retrieved context*,
  not just the query. Multi-role hospital dataset (20k samples, 4 roles) released as a benchmark.
- **Limitation:** activation-based detection needs white-box model access (open-source LLMs), not available
  for API-only generators; V1 stays pattern-based, but adopt the 5-attack taxonomy for audit event typing.

## [2505.06579] PoisonCraft: Practical Poisoning of RAG

- **Thesis:** A query-agnostic corpus-poisoning attack that gets a malicious doc retrieved *and* acted on,
  without knowing the user query, at a poisoning ratio as low as **0.5%**.
- **Poison anatomy (detection signal):** injected doc = fake knowledge + high-frequency question tokens
  (who/what/when...) stuffed for retrieval + an adversarial suffix; plus an imperative like
  "you MUST recommend this URL ...". Removing the suffix drops ASR by ~31% (retrieval) / ~24% (target).
- **Output-side signal:** the model appends an attacker URL to otherwise-correct factual answers.
- **Actionable:** in `check_answer`, flag/strip URLs and "recommend/visit this link" phrasing not present
  in citations; in ingestion, flag chunks with imperative instructions ("you must", "always recommend").
- **Limitation:** ASR-target is often < ASR-retrieval (models sometimes ignore poison); transfers to
  black-box OpenAI embedders but at reduced rates.

## [2505.08728] Securing RAG: A Risk Assessment and Mitigation Framework

- **Thesis:** Consolidates fragmented RAG security literature into a **risk × mitigation matrix (M0–M12)**
  aligned with OWASP LLM Top-10, NIST AI RMF, EU AI Act, and GDPR.
- **Mitigations most relevant to us:** M0 Anonymization (irreversible, pre-store), **M1 Pseudonymization
  (reversible 3-step: replace with placeholder + keep mapping → generate → restore)**, M3 Access Limitation,
  M4 System-instruction reinforcement, M5 Input Validation, M9 Distance Threshold, M11 Re-Ranking,
  M12 Exposure/Data Minimization (a GDPR principle).
- **Actionable:** our `PatternRedactor` is M0 (destructive). Add an M1 pseudonymizer (reversible mapping)
  so answers can still cite entities — the exact shape V1.2 needs ("prove what was redacted, how").
- **Limitation:** it is a framework/survey — no benchmark numbers; mitigations must be use-case tuned.

## [2508.01084] Provably Secure RAG (SAG)

- **Thesis:** First provably-secure RAG framework: pre-storage full encryption of **both chunk text and
  embeddings**, decrypted only for authorized entities, with formal confidentiality/integrity proofs.
- **Two schemes:** Chained Dynamic Key Derivation (sequential keys + hash-based tamper detection) vs.
  Isolated AES-CBC per node (lower latency, deployment flexibility). Roles hold distinct keys.
- **Actionable:** informs V1.2 access-control-log / data-lineage design — encryption + per-role key gating
  is the storage-layer analogue of our audit trail; keep it as an adapter-level (vectorstore) concern.
- **Limitation:** encryption at storage layer, out of scope for `basic_guard`/`redaction`; adds key-mgmt
  overhead. Belongs to adapters, not V1 domain guards.

## [2511.10128] RAGFort: Dual-Path Defense Against Knowledge-Base Extraction

- **Thesis:** Attackers reconstruct a proprietary KB by aggregating answers along two paths — *intra-class*
  (deep within a topic) and *inter-class* (spreading to related topics, e.g., the RAG-Thief agent). Defending
  only one path fails.
- **Defenses:** contrastive reindexing (inter-class isolation) + constrained cascade generation (intra-class);
  baselines = distance threshold, paraphrase/summarize retrieved content, limit top-k. Reduces chunk
  reconstruction rate from **57.16% → 27.96%** (Healthcare) while preserving answer quality.
- **Actionable:** extraction shows up as *many iterative, semantically-drifting queries from one client* —
  a per-session signal for the audit log and future rate/similarity monitoring.
- **Limitation:** structure-aware defenses require KB clustering, a V2+/retrieval concern, not V1 guards.

## [2602.06616] Confundo: Learning-to-Poison for Practical RAG

- **Thesis:** Prior poison attacks look strong only because evaluations skip the real ingestion pipeline;
  a fine-tuned "poison generator" stays effective after chunking and on paraphrased queries.
- **Defensive levers it must evade (so they work):** (1) **chunking fragments poison** — randomizing chunk
  size/boundaries weakens injected instructions; (2) **perplexity/fluency filters** catch unnatural text
  (attack adds a PPL reward to bypass); (3) poison is kept **short** to stay stealthy → unusually long
  injected instruction blocks are suspicious.
- **Actionable:** add an optional perplexity/fluency check + a chunk-length/imperative heuristic in ingestion;
  Confundo confirms these are real (if evadable) filters. Also usable defensively to watermark own web content.
- **Limitation:** perplexity filtering is evadable by design here; treat it as defense-in-depth, not a gate.

## [2603.21654] Towards Secure RAG: Comprehensive Review of Threats, Defenses & Benchmarks

- **Thesis:** First end-to-end survey mapping the whole RAG pipeline into a Threats / Defenses / Benchmarks
  taxonomy (Fig. 2), organized by *where in the pipeline* each control operates.
- **Threat vectors:** data poisoning (incl. perplexity-optimized, chain-of-thought, gradient, graph-RAG),
  **membership inference**, adversarial/jailbreak (query-time semantic evasion), **embedding inversion**,
  indirect injection.
- **Defense taxonomy (input vs output side):** input = dynamic access control, data cleansing/filtration,
  encryption, data fencing, adversarial pre-filtering; output = data masking, federated isolation,
  **differential-privacy perturbation**, lightweight sanitization.
- **Actionable:** use this taxonomy as the canonical vocabulary for audit-event `category` fields and to
  checklist coverage gaps (we have input filter + output redaction; membership-inference & embedding-inversion
  are uncovered).
- **Limitation:** survey, no new numbers; some defenses (homomorphic, federated) are far beyond V1.

## [2604.12201] AdversarialCoT: Single-Document Retrieval Poisoning for Reasoning

- **Thesis:** A **single** poisoned document embedding an adversarial chain-of-thought can steer a reasoning
  LLM to an attacker target answer in a black-box setting, improving ASR by up to **+23%** over batch poison.
- **Detection signal:** the poison mimics the model's own CoT structure (how it opens reasoning, transitions
  between evidence, aggregates) — retrieved chunks that read like *reasoning/instructions* rather than facts
  are suspect. Attacker can only add docs, not delete.
- **Actionable:** distance-threshold and flooding defenses are insufficient (one doc suffices); flag retrieved
  chunks containing reasoning-directive language ("therefore you should conclude...", step-by-step imperatives)
  and log them in the lineage trail.
- **Limitation:** query-specific and controlled setting; crude poison "can easily be filtered" — the threat is
  precisely the *fluent, evidence-shaped* poison that evades naive filters.

## [2604.20932] Adaptive Defense Orchestration (ADO): Sentinel–Strategist

- **Thesis:** An always-on defense stack is self-defeating — it cuts contextual recall by **41–46%**
  ("security-utility paradox"). Instead, detect risk per-query, then activate only warranted defenses.
- **Architecture (mirror this):** a **Sentinel** computes a per-query risk profile from lightweight signals —
  *lexical query overlap* + *vector-space dispersion among retrieved docs*; a **Strategist** maps the profile
  to defenses across enforcement hooks (retriever / post-retrieval / pre-generation / output).
- **Defenses toggled:** DP-RAG (perturb similarity to suppress membership signal), TrustRAG clustering (drop
  semantic-outlier / poisoned docs), attention-variance filter (prune over-dominant context / leakage).
- **Results:** eliminates membership-inference leakage; strongest variants cut poisoning ASR to ~0 while
  restoring recall to **> 75%** of undefended baseline.
- **Actionable:** this is the blueprint for a risk-score-driven guard chain — our `GuardResult.risk_score`
  should gate which guards run, not run everything always.

---

## Implications for this framework (V1 / V1.2)

Prioritized, mapped to real files. Each item cites the paper(s) it derives from.

1. **[V1, P0] Widen injection coverage beyond the 5 current regexes** in
   [`basic_guard.py`](../../src/modular_rag/security/filters/basic_guard.py). Add pattern families for
   *indirect/context-embedded instructions* ("you must recommend/visit", "always cite this URL",
   "therefore you should conclude"), and imperative reasoning-directives. These are the highest-signal
   textual markers of practical poison [2505.06579][2604.12201]. Keep regex as first-line only — the papers
   agree it is necessary but insufficient [2504.09593].

2. **[V1, P0] Implement `check_answer` (currently a no-op)** in
   [`basic_guard.py`](../../src/modular_rag/security/filters/basic_guard.py). Flag/strip URLs and
   "for more info visit ..." phrasing in answers that do not appear in any cited chunk — the dominant
   observable effect of corpus poisoning [2505.06579]. Emit a `TraceStep` per rule (`.instructions.md` §3).

3. **[V1, P1] Add a reversible pseudonymizer alongside the destructive `PatternRedactor`** in
   [`security/redaction/`](../../src/modular_rag/security/redaction/). Follow the 3-step M1 pattern
   (placeholder + mapping → generate → restore) so answers keep entity fidelity while raw PII never reaches
   logs/generator [2505.08728]. This is the exact primitive V1.2 needs to *prove what was redacted, how*.

4. **[V1, P1] Extend redaction patterns** in
   [`patterns.py`](../../src/modular_rag/security/redaction/patterns.py): today only email/phone-FR/IBAN/
   api_key. Add SSN-style national IDs, credit-card (with Luhn validation to cut false positives), and
   generic personal names via context — PII memorization/leakage is a named RAG risk in every survey
   [2504.09593][2603.21654].

5. **[V1.2, P1] Adopt a canonical attack taxonomy for audit-event typing.** Type each audit event by the
   ControlNet 2-domain / 5-attack model (breaching: reconnaissance, exfiltration, unauthorized access;
   poisoning: knowledge poisoning, conversation hijacking) [2504.09593], cross-referenced with the survey's
   input/output defense taxonomy [2603.21654]. Wire this into `security/audit/event_schema.py` (V1.2 plan).

6. **[V1.2, P1] Map mitigations to compliance frames in the audit trail.** M12 Data Minimization is a direct
   GDPR principle; anchor audit/compliance reporting to OWASP LLM Top-10 + NIST AI RMF + EU AI Act as the
   survey recommends [2505.08728]. Store redaction proof (pattern id + replacement, never raw PII) per
   ROADMAP V1.2.

7. **[V1.2, P2] Log per-session extraction/reconnaissance signals.** Many iterative, semantically-drifting
   queries from one client indicate KB-extraction; capture lexical-overlap and count signals in the
   access-control log for later rate/anomaly review [2511.10128][2603.21654]. No blocking logic in V1 — just
   observability, which is already mandatory.

8. **[V1, P2] Add an optional ingestion-side poison heuristic** (in `ingestion/`, an allow-zone): flag chunks
   that are unusually long *and* imperative, or that read as reasoning/instructions rather than facts; a
   perplexity/fluency check is a valid (evadable) defense-in-depth layer [2602.06616][2604.12201]. Chunk-size
   randomization already fragments poison as a free side benefit [2602.06616].

9. **[V1→V2, P2] Make `GuardResult.risk_score` actually drive a guard chain.** The ADO result is decisive:
   always-on defenses cut recall 41–46%; a Sentinel-style per-query risk score should gate *which* guards run
   [2604.20932]. In V1, keep the current 0.9/0.8/0.5 scale but calibrate it to this model; the full
   Sentinel–Strategist split belongs to V2's orchestration/policy layer, not V1 guards.

10. **[Backlog] Note uncovered threat classes.** Membership inference and embedding inversion have **no** V1
    control [2603.21654][2604.20932]; storage-layer encryption of chunks+embeddings [2508.01084] and DP/
    clustering retrieval defenses [2604.20932] are adapter/retrieval concerns. Record as ADR candidates rather
    than V1 guard work (per CLAUDE.md §07: ADR before structural change).
