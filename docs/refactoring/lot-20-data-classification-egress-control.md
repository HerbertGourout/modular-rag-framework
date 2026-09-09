# Lot 20 — Data Classification and LLM Egress Control

**Status:** COMPLETE. Engineering scope closed 2026-09-08, corrected after Codex review pass 1
(`CHANGES_REQUIRED` — 4 HIGH, 1 MEDIUM; see §8), then further revised the same day after HIGH-001's
initial "keep opt-in" disposition was reversed by explicit user decision (see §8). Remote-provider
egress is now fail-closed by default for this framework's own known remote provider types.
[ADR-0016](../adr/0016-provider-egress-control.md) drafted (Proposed) 2026-09-08 in response to
HIGH-004, revised the same day to record the HIGH-001 reversal, and **Accepted by Herbert Gourout
2026-09-09** — the last open item this lot had, per the "not self-granted" convention every prior
lot in this programme uses (see §7). No open items remain.

## 1. What this closes

`docs/architecture/threat-model.md` and `docs/architecture/data-classification-policy.md` both
named the same gap: `PatternRedactor` runs on generated answer text, after the model has already
produced a response — it cannot stop raw document/chunk content from reaching a remote embedder
or generator *before* that call happens. This lot adds that missing, fail-closed checkpoint.

## 2. What shipped

### 2.1 Classification is now a real, propagated field

- `core.enums.DataClassification` (public/internal/confidential/restricted) is no longer pure
  vocabulary. `core.enums.classification_rank()`/`combined_classification()` give it a strict
  ordering and a many-values-to-one reduction rule: `None` (unclassified) in any input makes the
  combined result `None`, never silently the lowest (`public`) level.
- `Document.classification`/`Chunk.classification: DataClassification | None = None` — same
  optional, explicit, caller-supplied pattern `tenant_id` already established at Lot 11b. Nothing
  in this codebase infers a classification from content; an operator sets it at ingestion.
- `FixedSizeChunker`/`AdaptiveChunker` propagate `document.classification` onto every `Chunk`
  they produce, mirroring the existing `tenant_id` propagation exactly.

### 2.2 The egress contract and reference policy

- `contracts/egress.py`: `EgressOperation` (`EMBED`/`GENERATE`/`RERANK`), `EgressDecision`
  (content-free — `allowed`, `reason`, `classification`, `provider`, `operation`, nothing else),
  `EgressPolicy` Protocol (`check(classification, provider, operation) -> EgressDecision`).
  Vendor-neutral by construction: no provider name appears in this module.
- `security.policies.egress_policy.ManifestEgressPolicy`: the reference implementation.
  `providers: dict[str, {local: bool, max_classification?: str}]` + `default_classification`
  (defaults to `"restricted"`, matching data-classification-policy.md's own recommended default
  for unclassified content). Fail-closed at every decision point:
  - a `local: true` provider is always allowed, any classification;
  - a provider with no entry in `providers` is always denied;
  - a non-local provider missing `max_classification` is rejected at **construction**
    (`ConfigurationError`), not silently permissive;
  - unclassified content (`None`) resolves to `default_classification` before the ceiling check.
- `provider` is the manifest's `ComponentConfig.type` string (e.g. `"sentence-transformers"`,
  `"openai"`), not the component's own `.name()` — `HuggingFaceEmbedder.name()`/
  `OpenAIEmbedder.name()` are dynamic and model-specific (`f"hf-{model}"`), which would make a
  policy-config key silently drift every time an operator changed a `model:` value.

### 2.3 Enforcement points

| Checkpoint | Where | Classification input |
|---|---|---|
| Embedding (ingestion) | `RAGEngine.ingest_chunks()`, before the embed loop | `chunk.classification`, per chunk |
| Embedding (query, retrieval) | `RAGEngine._retrieve()`, before `Retriever.retrieve()`; `LangGraphEngineAdapter._node_retrieve()`, before the same call | `None` (unclassified) — `Query` carries no classification field, so this always resolves through the policy's `default_classification` |
| Reranking | `RAGEngine._run_steps()`, before the reranker runs | `combined_classification()` of retrieved context |
| Generation (native) | `RAGEngine._run_steps()`, before `Generator.generate()` | `combined_classification()` of retrieved context |
| Generation (delegated) | `LangGraphEngineAdapter._node_generate()`, before `Generator.generate()` | `combined_classification()` of `state["chunks"]` |

The query-embedding row closes Codex review pass 1's HIGH-002: the retriever embeds the query
text internally (`retrieval.retrievers.vector.VectorRetriever.retrieve()`, reached by
`HybridRetriever` too) before ever reaching the generation checkpoint — both `answer()` and the
standalone `retrieve()` (used by `/retrieve`) previously had zero protection for this call, since
`retrieve()` never reaches a generation check at all. All six checkpoints raise
`EgressDeniedError` (new, `core.errors.SecurityError` subclass) on denial, before
the guarded call executes — proven by `_RecordingEmbedder.calls == []` /
`_FakeGenerator.received_context == []` assertions in the new tests, not merely inferred from
the control flow. `EgressDeniedError` inherits every existing `SecurityError` handler for free:
`api/errors.py::to_http_exception()` maps it to HTTP 403 with its own safe message;
`cli/__init__.py::_exit_code_for()` maps it to exit code 3. Both are covered by a dedicated
regression test (`tests/unit/api/test_api.py`, `tests/unit/cli/test_cli.py`) even though the
underlying mapping needed no new code — the task's own explicit "typed, safe errors" acceptance
criterion asked for proof, not just inheritance.

Native and LangGraph share `Container.egress_policy` and the identical `manifest.generator.type`
input — `test_parity_with_native_adapter_on_an_egress_denial` proves both adapters deny the same
manifest identically, the same parity bar `.claude/rules/orchestration.md` already holds guard
denial to.

### 2.4 Manifest wiring

- `GovernanceSection.egress_policy: ComponentConfig | None = None` — additive, optional, same
  shape as every other governance role.
- `app/default_factories.py` registers `("egress_policy", "manifest") -> ManifestEgressPolicy`.
- `orchestration/registry.py::runtime_manifest_errors()`: when `governance.egress_policy` is
  configured, every wired embedder/generator/(reranker if present) `type` must have a matching
  `providers[...]` entry, checked from the raw manifest config — not by constructing
  `ManifestEgressPolicy` (orchestration/ may import only `core/`+`contracts/`+`orchestration/`,
  never `security/`). A manifest missing coverage fails at `wire()`, before any request reaches
  the deny-by-default runtime path. `app/config_resolution.py::validate_capabilities()` also
  dry-run-checks the `type:` itself against the registry, same as every other role.
- **Fail-closed at `wire()` for known remote provider types (HIGH-001 reversal, 2026-09-08).**
  `runtime_manifest_errors()` also runs this check **unconditionally**, not only when
  `governance.egress_policy` is present: a module-level `_KNOWN_REMOTE_PROVIDER_TYPES = frozenset({
  "openai", "anthropic", "openai-embeddings"})` names this framework's own built-in remote
  provider types. If a manifest wires one of these for its embedder/generator/(reranker if
  present) and `governance.egress_policy` is either absent entirely or present but missing that
  provider's entry, `wire()` fails — the manifest cannot load. Any other, unrecognized `type:`
  string (including every synthetic `"fake-*"` provider the test suite uses) is unaffected: no
  collateral restriction, verified empirically by running the full suite before touching any
  preset/fixture, which produced exactly the 5 failures attributable to the 3 shipped presets and
  one CLI test — no unexpected breakage. Deliberately scoped to a small, explicit allowlist in
  `orchestration/registry.py`, not `contracts/egress.py` — CLAUDE.md §07 forbids hard-coding
  vendor names into `contracts/`; `registry.py` already hardcodes `{"native", "langgraph"}` for
  `engine.adapter`, so this follows existing precedent rather than creating a new one. See §8 for
  the full HIGH-001 reversal record.
- Consumed identically under `engine.adapter: native` and `engine.adapter: langgraph` —
  deliberately **not** added to `runtime_manifest_errors()`'s LangGraph-unsupported list (unlike
  `policy_engine`/`review_queue`/`audit_sink`/`feedback_sink`), since the task's own acceptance
  criterion required protecting the delegated-engine handoff, not exempting it.

### 2.5 Audit and observability

- `AuditEventType.EGRESS_DECISION`, five new `AuditEvent.payload` allowlist keys
  (`egress_decision`, `egress_reason`, `egress_provider`, `egress_classification`,
  `egress_operation`) — content-free by construction (`EgressDecision` has no free-text field
  beyond the bounded `reason` string, itself built only from classification/provider/operation
  names, never caller content).
- Recorded for **both allowed and denied** decisions (Codex review pass 1, MEDIUM-001 — the
  original design audited denials only, matching `GUARD_DECISION`'s convention; the finding
  correctly noted that "why was this allowed" is also a real compliance question, not answerable
  from a `RUN_SUCCEEDED` event alone). `ingest_chunks()`'s per-chunk loop aggregates allowed
  evidence to at most one event per unique `(classification, provider)` pair actually observed in
  the batch — enforcement still runs per chunk (a denial on chunk 50 of 100 still stops the
  batch), only the *evidence* is deduplicated, so a large, fully-permitted ingest batch does not
  produce one audit row per chunk. The three single-check checkpoints (query embedding, reranking,
  generation) have no such loop, so no aggregation is needed there.
- `mrag.egress.allowed`/`mrag.egress.denied` counters (operation/provider attributes, no
  identifiers).
- `RAGEngine._audit_egress()` records evidence for any decision; `_enforce_egress()` wraps it and
  raises on denial — every single-check checkpoint calls `_enforce_egress()`, `ingest_chunks()`'s
  loop calls `_audit_egress()` directly so it can apply its own aggregation. Ingestion uses one
  shared correlation id per `ingest_chunks()` call (no `Trace` exists at that call site), the
  retrieval/generation/reranking paths reuse `trace.id` like every other audit call in that class.
  `LangGraphEngineAdapter` does not audit — unchanged, matches its own documented scope boundary
  ("does not replicate `RAGEngine`'s audit-event emission... belongs above the `DocumentEngine`
  boundary"). Codex review pass 2 named this gap explicitly for the two egress checkpoints
  specifically (pass-2 MEDIUM-001, re-numbered from pass 1's MEDIUM-001 which this closed for the
  native engine only): LangGraph's egress *enforcement* is correct (both checkpoints deny/allow
  identically to the native path), but produces no audit evidence. Presented to the user as a
  scope-expansion decision (closing it means either reversing `registry.py`'s existing rejection
  of `governance.audit_sink` under `engine.adapter: langgraph`, or inventing a new adapter-local
  audit mechanism outside this adapter's documented Lot 15 boundary) — **user confirmed: defer,
  accept as documented risk**, consistent with every other audit-eligible event this adapter
  already doesn't record. See `.review/handoff.md`'s "Final Claude remediation" section for the
  full record.

## 3. Backward compatibility

Every one of the 1411 pre-existing unit/contract tests still passes unmodified for any manifest
that does **not** wire one of this framework's own known remote provider types — confirmed
directly, not assumed: `test_ingest_chunks_without_egress_policy_configured_is_unaffected` and
`test_answer_without_egress_policy_configured_is_unaffected` construct a `RESTRICTED`-classified
chunk with **no** `governance.egress_policy` configured and a non-remote (`"fake"`) provider, and
assert the pipeline behaves exactly as it did before this lot.

**Revised after the HIGH-001 reversal (2026-09-08):** this no longer holds unconditionally for the
three shipped presets. All three (`local-hybrid-rag.yaml`, `secure-enterprise-rag.yaml`,
`langgraph-rag.yaml`) use `embedder.type: sentence-transformers` (local) with
`generator.type: openai`/`anthropic` (a known remote type) — each now carries an explicit
`governance.egress_policy` with `max_classification: restricted` for that provider, added as part
of this reversal. Runtime request-handling behavior for these presets is unchanged (no real
classification data flows through any of them today, so the ceiling check never actually denies
anything in current usage) — but a **manifest that omits this block and wires a known remote
provider type now fails at `wire()`**, where it previously loaded successfully. This is the
intended, accepted consequence of closing HIGH-001, not an unintended compatibility break: see §8.

## 4. Tests added

| File | Covers |
|---|---|
| `tests/unit/core/test_enums.py` (new) | `classification_rank()`/`combined_classification()` |
| `tests/unit/security/policies/test_egress_policy.py` (new) | `ManifestEgressPolicy`: local/remote, ceiling comparison, unknown provider, unclassified default, construction-time fail-closed validation |
| `tests/contract/test_egress_conformance.py` (new) | `EgressPolicy` Protocol conformance, cross-implementation fail-closed invariants |
| `tests/unit/contracts/test_manifests.py` | `GovernanceSection.egress_policy` schema |
| `tests/unit/orchestration/test_registry.py` | `wire()` rejects a manifest missing provider coverage for embedder/generator/reranker; accepts full coverage; `Container.egress_policy` defaults to `None` |
| `tests/unit/app/test_config_resolution.py` | `validate_capabilities()` catches a typo'd `egress_policy.type` |
| `tests/unit/orchestration/test_engine.py` | Embed (ingestion + query)/generate/rerank deny+allow, zero-adapter-calls-on-deny, allow+deny audit/meter evidence, per-batch allow aggregation, backward compatibility |
| `tests/unit/adapters/llms/test_langgraph_engine.py` | Same deny/allow/local-always-allowed behavior (including query-time embedding) on the delegated engine, native/LangGraph parity |
| `tests/unit/adapters/vectorstores/test_qdrant_store.py`, `test_qdrant_sparse_store.py` | `Chunk.classification` persisted on `index()` and reconstructed on retrieval, for both dense and sparse stores |
| `tests/unit/api/test_api.py`, `tests/unit/cli/test_cli.py` | `EgressDeniedError` → HTTP 403 / CLI exit 3 |

## 5. Not delivered — explicit, not silent

- **No pseudonymization / reversible token mapping.** `docs/refactoring-plan.md`'s full Lot 20
  scope described locally pseudonymizing PII/secrets before an *allowed* remote call, with an
  encrypted, short-lived, audit-invisible token mapping. Not built — an allowed call still sends
  the real content, unmodified (matching this codebase's existing `PatternRedactor`, which is
  answer-side only and separately opt-in).
- **No richer provider capability profiles.** A profile is `{local, max_classification}` only —
  no retention/residency/feature-eligibility/DPA modeling. `docs/refactoring-plan.md`'s gap-matrix
  entry for that remains explicitly a deployment-owner/DPO decision, not something code can infer.
- **Not covered:** PostgreSQL (audit/lifecycle/feedback/review sinks) and any other outbound
  connection this framework makes outside the `Embedder`/`Generator`/`Reranker`/delegated-engine
  boundary named above.

## 6. Checks that could not run in this sandboxed environment

No Qdrant, PostgreSQL, or LLM API key is available here. `tests/integration/`/`tests/e2e/` were
not run against this change — nothing in this lot's diff touches those adapters' own contracts
(no `Indexer`/vector-store/PostgreSQL-adapter signature changed), so the risk is low, but it is
unverified, not silently assumed safe. `scripts/run_benchmark.py`'s offline golden-set benchmark
was also not re-run — no `eval/` code path changed.

## 7. Sign-off

**Given — Herbert Gourout, 2026-09-09.** Sign-off is Herbert Gourout's to give, per
`docs/refactoring/lot-0-baseline.md` §2's sole decision authority — not self-granted, same
convention every completed lot in this programme has followed. Two decisions were explicit
(§8): HIGH-001 was initially confirmed opt-in on 2026-09-08, then that decision was explicitly
reversed the same day — remote-provider egress is now fail-closed by default for this framework's
own known remote provider types; HIGH-004's [ADR-0016](../adr/0016-provider-egress-control.md)
was drafted 2026-09-08 and **Accepted 2026-09-09** ("j'accepte l'ADR 0016"). Lot 20 has no open
items remaining.

## 8. Codex review pass 1 — findings and corrective actions

Full review: `.review/codex-review.md`. Status `CHANGES_REQUIRED`, 4 HIGH + 1 MEDIUM, 0 BLOCKER.
Independently re-verified against the code before any fix — not applied blindly.

| Finding | Disposition | Resolution |
|---|---|---|
| HIGH-001 — remote providers with no `governance.egress_policy` configured remain fully open | Valid, confirmed | **Escalated; resolved by user decision, 2026-09-08, then reversed the same day.** Initially: making remote-provider egress fail-closed by default would break all three shipped presets and `examples/simple_qa/`, conflicting with CLAUDE.md's non-negotiable "must not break `examples/simple_qa/`" priority — presented as a security-policy decision, **confirmed: keep opt-in, accept the residual risk.** **Reversed the same day** on explicit user instruction ("traiter le problème de HIGH-001"): the opt-in gap was judged unacceptable. **Fixed** — `orchestration/registry.py::runtime_manifest_errors()` now rejects, at `wire()`, any manifest that wires one of this framework's own known remote provider types (`openai`, `anthropic`, `openai-embeddings`, scoped via a new `_KNOWN_REMOTE_PROVIDER_TYPES` allowlist) without a covering `governance.egress_policy` entry — resolving the CLAUDE.md conflict by updating all three shipped presets and `examples/simple_qa/`'s manifest to configure `governance.egress_policy` (`max_classification: restricted`, preserving current runtime behavior) rather than by leaving the gap open. Any unrecognized provider `type:` (including every test double) is unaffected — verified empirically, zero collateral test failures beyond the 3 presets + 1 CLI test predicted by the design. See §2.4, §3. Documented in [ADR-0016](../adr/0016-provider-egress-control.md) §2 as a superseded-and-revised decision, not a silently rewritten one. |
| HIGH-002 — query-time embedding bypasses the egress policy | Valid, confirmed | **Fixed.** New checkpoint in `RAGEngine._retrieve()` (shared by `answer()` and `retrieve()`) and `LangGraphEngineAdapter._node_retrieve()`, before the retriever's internal embed call. `classification=None` always (`Query` has no classification field), resolving through the policy's existing `default_classification` — no new manifest field invented. See §2.3. |
| HIGH-003 — Qdrant adapters drop `Chunk.classification` on the real persisted round trip | Valid, confirmed — a real correctness bug, not a design gap | **Fixed.** `classification` added to both dense (`qdrant_store.py`) and sparse (`qdrant_sparse_store.py`) `index()` payloads and retrieval reconstruction, mirroring the existing `tenant_id` pattern exactly (which had the identical bug shape at Lot 12b, already fixed there). |
| HIGH-004 — new public `contracts.egress` Protocol added without an ADR | Valid, confirmed — restates this document's own §5/§7 disclosure | **Fixed.** Presented to the user as a public-contract decision; user chose to have a Proposed-status ADR drafted for their own review rather than leave the gap undocumented. [ADR-0016](../adr/0016-provider-egress-control.md) drafted 2026-09-08, **Accepted by Herbert Gourout 2026-09-09**. |
| MEDIUM-001 — allowed egress decisions are not auditable | Valid, confirmed | **Fixed, in scope.** `_audit_egress()`/`_enforce_egress()` record both outcomes; `ingest_chunks()` aggregates allowed evidence to one event per unique `(classification, provider)` pair per batch to bound volume, per the finding's own recommended action. See §2.5. |

HIGH-001 is fixed in code (fail-closed by default for known remote provider types), not merely a
ratified accepted-risk decision — the reversal itself is documented in ADR-0016 §2 as a revised
decision, superseding the original 2026-09-08 acceptance. HIGH-004 is closed: ADR-0016 is
Accepted, not merely drafted — see `.review/handoff.md` and §7 above. Every finding from Codex
review pass 1 now has a final, closed disposition; no items remain open for this lot.
