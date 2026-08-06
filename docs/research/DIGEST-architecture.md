# Architecture Research Digest

> Auto-distilled from `.claude/research-papers/advanced_architecture/` on **2026-07-12**.
> Source PDFs: 3 arXiv preprints. Each section below is a compressed reading; consult the
> original PDF before acting on any single claim. Nothing here changes source code — it feeds
> [ROADMAP.md](../../ROADMAP.md) and the ADRs under [docs/adr/](../adr/).

---

## [2604.11623v3] Context Kubernetes: Declarative Orchestration of Enterprise Knowledge for Agentic AI

**Thesis.** The durable, high-value layer for agentic AI is not the LLM but a Kubernetes-style
*orchestration layer* for organizational knowledge — declarative, permission-governed, and continuously reconciled.

**Patterns & reported benefits.**
- **Knowledge-Architecture-as-Code**: a version-controlled YAML manifest declares sources, permissions,
  freshness, routing, guardrails (7 sections). Directly mirrors this framework's manifest-driven wiring.
- **Reconciliation loop**: continuously diffs declared vs. observed state; freshness detection in <1 ms,
  20-source reconcile in 23 ms. Blocks stale/phantom content that ungoverned RAG serves silently.
- **CxRI (Context Runtime Interface)**: 6-op adapter (connect/query/read/write/subscribe/health) decoupling
  orchestration from any store — a tight analogue of Kubernetes CRI and of this repo's adapter/Protocol split.
- **Three-tier agent permission model** with the invariant *agent authority ⊂ human authority*, enforced at
  registration; fail-closed on Permission-Engine outage. Only the 3-tier model blocked all 5 attack scenarios
  (flat RBAC blocked 4/5). TLA+ verified safety over 4.6M states.

**Limitations.** Prototype only (92 tests, synthetic 10-person seed data, no real deployment); rule-based
routing 63% / LLM-assisted 75% domain accuracy — governance holds at any accuracy but *utility* needs ≥90%.
Probabilistic LLM routing can violate governance guarantees (their deepest open tension).

## [2604.20666v1] ORPHEAS: A Cross-Lingual Greek–English Embedding Model for RAG

**Thesis.** A domain-specialized bilingual embedder, fine-tuned on knowledge-graph-derived pairs with
cross-lingual augmentation, beats general multilingual models without sacrificing English retrieval.

**Patterns & reported benefits.**
- **KG-based fine-tuning data generation**: an ontology (DOCUMENT→CHUNK→ENTITY/ATOMIC_FACT/QUESTION) yields
  semantically coherent anchor-positive pairs, outperforming naive synthetic query-doc pairs.
- **Cross-lingual augmentation**: translate anchors both directions so one unified model serves monolingual +
  cross-lingual retrieval; measured with **Acc@k and NDCG@k (k=3,10)** — the exact metrics V1.1 eval targets.
- Fine-tuned E5-base (278M) tops mGTE/E5/MPNet/MiniLM on Greek + cross-lingual benchmarks; the dataset (not the
  backbone) drives most of the gain, validated by swapping in a weaker backbone.

**Limitations.** Single language pair; no chunk-size sensitivity study; gains depend on KG-extraction quality
(LLM cost). Confirms multilingual generalists degrade on morphologically complex, lower-resource languages.

## [2604.20452v1] HaS: Accelerating RAG through Homology-Aware Speculative Retrieval

**Thesis.** Retrieval — not generation — is the RAG latency bottleneck; a speculative "draft-then-validate"
layer over restricted scopes can bypass full-database search when a *homologous* prior query is re-identified.

**Patterns & reported benefits.**
- **Two-channel fast retrieval** (cache channel of prior results + narrow aggressive-ANNS "fuzzy" channel),
  merged and re-ranked into a draft — analogous to a caching + fusion stage in front of the retriever.
- **Homology validation as query re-identification**: accept the draft iff a cached query shares ≥τ document
  overlap (via a document→query inverted index), avoiding costly per-doc LLM verification (CRAG-style).
- **Plug-and-play**: 23.74%/36.99% retrieval-latency cut for only 1–2% accuracy drop; composes with IVF/ScaNN
  for a further 7–28%; amplifies gains on agentic multi-hop pipelines with query decomposition.

**Limitations.** Depends on real-world entity-popularity (homologous queries prevalent); degrades on scattered
datasets (SQuAD). Fuzzy channel must load the full DB (storage cost) unless compressed. k has a U-shaped
optimum (k=10); τ trades latency for accuracy. Validation is a *surrogate* — not exact groundedness.

---

## Implications for this framework

Prioritized, mapped to modules/ADRs. **[V1]** = actionable now; **[V2+]** = roadmap-only, keep out of V1 code.

1. **[V1] Strong external validation of manifest-driven wiring + adapter/Protocol split.** Context Kubernetes's
   Knowledge-Architecture-as-Code manifest and CxRI adapter interface are near-isomorphic to
   [ADR-0002 contracts-and-plugins](../adr/0002-contracts-and-plugins.md) and `orchestration/registry.py` +
   YAML presets. No code change — cite 2604.11623 in ADR-0002 as prior-art confirmation and keep resisting
   Python-level wiring.

2. **[V1] Adopt Acc@k + NDCG@k(3,10) as the golden-set metric contract.** ORPHEAS's evaluation protocol
   (2604.20666) is exactly the shape V1.1 `contracts/evaluation.py` / `eval/metrics/` should standardize —
   report both shallow (k=3) and extended (k=10) depth. Lock it in before writing V1.1 metrics.

3. **[V1] Keep the embedder strictly swappable behind its Protocol.** 2604.20666 shows domain/language-specialized
   embedders can beat generalists; `adapters/embeddings/` (hf_embedder, openai_embedder) must stay
   drop-in-replaceable so a future specialized model needs zero orchestration change. Verify the embedding
   Protocol in `contracts/` exposes only encode-level surface — no backbone assumptions leak upward.

4. **[V2+] Fail-closed governance + agent-authority-subset invariant → security/policies.** The three-tier
   permission model and *P_agent ⊂ P_human* invariant (2604.11623) are the sharpest design input for
   [ADR-0003](../adr/0003-security-and-governance.md) and the V2.0 Policy Engine. Record in ROADMAP now;
   do **not** add policy enforcement to V1. Adopt fail-closed (deny on policy-engine outage) as an explicit
   V2 requirement.

5. **[V2+] Reconciliation loop + freshness state machine for the audit/ingestion story.** The declared-vs-observed
   reconcile with fresh/stale/expired/conflicted states (2604.11623) is a concrete blueprint for V1.2
   `security/audit/data_lineage_tracker.py` and stale-source detection. Flag for ROADMAP under V1.2/V2; it is
   *not* V1.0 core-RAG scope.

6. **[V2+/V3] HaS speculative-retrieval as a caching layer, not a V1 retriever.** The draft-then-validate,
   two-channel design (2604.20452) maps cleanly onto the V3.1 `orchestration/query_cache.py` (hash/similarity
   cache) and a future speculative wrapper around `retrieval/`. Its plug-and-play, multi-hop amplification also
   informs `orchestration/state_machine.py` and whatever routing/flow logic the selected external engine exposes
   through the `DocumentEngine` port (per ADR-0005 — the native `router.py`/`flow_compiler.py` this note
   originally pointed at were removed in Lot 17, zero consumers; see
   `docs/refactoring/lot-17-prototype-retirement.md`). Keep out of V1 — it optimizes cost/latency, which the
   roadmap defers to V3.1.

7. **[V1, caution] Treat LLM-assisted query routing as utility, not a safety boundary.** 2604.11623's finding —
   governance must operate *below and independent of* probabilistic routing (guarantees hold even at 0% routing
   accuracy) — remains a live design rule even though the native `QueryRouter`/`orchestration/router.py` this
   note originally named were removed in Lot 17 (zero consumers, never wired). Apply it wherever routing
   decisions actually happen today: `TenantPolicy`/`SecurityGuard` enforcement in `RAGEngine.answer()` and in
   `LangGraphEngineAdapter`'s graph nodes must never be gated by, or downstream of, a routing/classification
   step — see the tenant-isolation bug found and fixed in `LangGraphEngineAdapter._node_retrieve()` (Lot 18,
   `docs/refactoring-plan.md`) for a concrete instance of exactly this coupling failure mode.
