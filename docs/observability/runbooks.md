# Runbooks

One section per alert in `alerts.yaml`, plus troubleshooting guidance for the readiness/review
signals that are not yet safe to alert on (ADR-0013). Each follows the same shape: what the signal
means, what to check first, what action to take, and
what NOT to do. Mirrors the procedural, honestly-scoped style already established by
`docs/guides/backup-restore.md` (Lot 16c) — concrete commands and checks, not vague guidance, and
explicit about what hasn't been validated against live infrastructure in this repository's own
development environment.

---

## mrag-high-error-rate

**Alert:** `MRAGHighErrorRate` — more than 5% of application-service calls for one `operation` are failing.

**What it means:** A real, unhandled exception is propagating out of `ApplicationService.answer()`
or `.retrieve()` for a meaningful fraction of traffic — not necessarily an intentional denial (see
"Does not cover" in `slo.md` §1).

Requests rejected by HTTP middleware before they enter `ApplicationService` are outside both the
numerator and denominator of this alert.

**First checks:**
1. Break down by `error_type` (the alert's own label) — `mrag_request_errors_total` grouped by
   `error_type` tells you immediately whether this is `SecurityError`/`PolicyViolationError`
   (intentional denials, check `mrag.guard.rejections` instead — this alert firing alongside a
   guard-rejection spike is a different incident than this alert firing alone) versus something
   else (`RetrievalError`, a provider SDK exception, an unexpected `KeyError`/`ValueError`).
2. Check `/ready` directly — is a dependency reporting unhealthy? Do not infer recovery from the
   current `mrag_readiness_state` gauge; its old labelled states are not reset.
3. Check recent deploys/config changes — a manifest change (a new `generator.config.model` that
   doesn't exist, a wrong `indexer.config.url`) is a common, fast-to-confirm root cause.
4. Check the LLM/vector-store provider's own status page if `error_type` points at a provider SDK
   exception.

**Action:** If a dependency is down, this resolves once that dependency recovers (see
`mrag-unready`). If a bad config/deploy is the cause, roll back. If the provider itself is down and
no fallback exists, this is a genuine outage — communicate accordingly; there is no automatic
fallback generator/retriever configured by default in this codebase.

**Do NOT:** silence the alert by lowering the threshold without first confirming the root cause —
this metric's whole purpose is catching exactly this class of regression.

---

## mrag-high-latency

**Alert:** `MRAGHighP95LatencyAnswer` and `MRAGHighP95LatencyRetrieve` — p95 latency exceeds
5 seconds for `answer` or 1 second for `retrieve`, respectively, for 10 minutes.

**What it means:** Requests are slow, not necessarily failing outright.

**First checks:**
1. For `/answer`: check whether the slowdown correlates with `mrag.generation.tokens` — a spike in
   `output` tokens (longer generated answers) or a provider-side slowdown both show up here, and
   are easy to conflate; compare against the LLM provider's own status/latency dashboards if
   available.
2. For `/retrieve`: check `mrag.retrieve.degraded` — a down vector or lexical leg forces
   `HybridRetriever._safe_retrieve()` through its full timeout before falling back, which shows up
   as added latency on *every* request during the outage window, not just the ones that end up
   `empty`.
3. Check the API or reverse proxy's own latency for a concurrency bottleneck. This histogram starts
   inside `ApplicationService`, after `ConcurrencyLimitMiddleware`, so middleware queueing is not
   visible in `mrag.request.duration_ms`.

**Action:** If provider-side, this is largely outside this codebase's control beyond model/timeout
configuration. If a retrieval leg is down, see `mrag-retrieval-degraded`. If concurrency-bound,
consider whether the deployment is under-provisioned for current load.

**Do NOT:** raise the alert threshold as a first response — confirm root cause first per `slo.md`
§2's stated target.

---

## mrag-retrieval-degraded

**Alert:** `MRAGRetrievalDegraded` — the `vector` or `lexical` retrieval leg is failing on real
requests.

**What it means:** `HybridRetriever._safe_retrieve()` is catching a real exception from one leg and
returning an empty result for that leg only — the request still completes (with reduced recall),
it does not fail outright.

**First checks:**
1. Check `/ready`'s per-role dependency detail for `indexer`/`retriever` — a down leg usually also
   shows up there, though `/ready` computes health from a periodic probe while this metric reflects
   *actual request traffic* hitting the same failure; the two can briefly disagree.
2. Check whether this is the `vector` leg (Qdrant) or `lexical` leg (in-memory BM25 or a persistent
   sparse Qdrant collection, per `retriever.config.lexical`).
3. Check the affected store's own logs/metrics directly (Qdrant connection errors, timeouts).

**Action:** Restore the affected store. There is no automatic remediation in this codebase for a
degraded leg — it degrades gracefully (keeps serving from the healthy leg) but does not self-heal
the unhealthy one.

**Do NOT:** assume this alert alone means the pod should be pulled from rotation — `/ready` (not
this metric) is the authoritative "should this pod serve traffic" signal, and intentionally stays
`DEGRADED` (200, still routable), not `UNREADY`, for exactly this scenario (see
`orchestration/container.py`'s own `_CRITICAL_ROLES` design note).

---

## mrag-empty-fetch

**Alert:** `MRAGHighEmptyFetchRate` — more than 20% of requests for an operation return zero
chunks.

**What it means:** Either the corpus genuinely lacks relevant content for a sustained burst of
queries, or something is structurally broken (wrong collection name, wrong tenant filter, an
ingestion gap).

**First checks:**
1. Check `mrag.ingest.chunks`/`mrag.ingest.documents` — did ingestion volume drop or stop
   recently? A stale/empty index is the most common root cause.
2. Check whether the spike correlates with a specific `tenant_id`'s traffic (not visible in these
   metrics directly, per the cardinality-safety design — check application logs/traces for this
   instead) — a newly onboarded tenant with no ingested content yet is a common, benign cause.
3. Manually run a few of the affected queries against `/retrieve` directly and inspect results.

**Action:** If ingestion stopped, resume it. If it's a genuine corpus gap for new content/tenants,
this may not be actionable beyond ingesting the missing content.

**Do NOT:** treat every empty-fetch spike as an incident — some baseline rate is expected for
genuinely out-of-corpus queries; the 20%/15-minute threshold is tuned to catch *sustained,
structural* gaps, not normal variance.

---

## mrag-unready

**Inactive reference signal:** no `MRAGUnready` rule is shipped. The current readiness gauge can
retain an old `unready=1` series after recovery because other state labels are not reset.

**What it means:** A critical dependency (`generator`, `audit_sink`, `egress_policy` when it
probes a decision service such as OPA, or both `indexer` and `retriever` simultaneously) is
failing its health probe. An orchestrator should already be routing
traffic away from this pod (HTTP 503).

**First checks:**
1. `GET /ready` directly and read the `dependencies` array in the response — it names exactly
   which role(s) are unhealthy and the (sanitized, non-sensitive) failure detail
   (`core.resilience.unhealthy_dependency()` — see `.claude/rules/health-checks.md` rule 9).
2. For `generator`: check the configured LLM provider's credential validity and service status —
   `OpenAIGenerator`/`AnthropicGenerator`'s own `check_health()` makes a real, cached,
   authenticated call (`.claude/rules/health-checks.md` rule 10).
3. For `audit_sink` (PostgreSQL-backed): check database connectivity/credentials directly.
4. For simultaneous `indexer`+`retriever`: check the shared Qdrant instance both legs point at
   (common in `secure-enterprise-rag.yaml`-style manifests where both roles hit the same server).

**Action:** Restore the failing dependency. This is the highest-severity alert in this set —
treat as a live incident, not a backlog item.

**Do NOT:** manually force traffic back to an `UNREADY` pod — the fail-closed design exists
specifically so a broken generator/audit path doesn't silently serve degraded/unaudited answers.

---

## mrag-degraded-sustained

**Inactive reference signal:** no `MRAGDegradedSustained` rule is shipped for the same sticky-label
limitation described above. Diagnose the live `/ready` response directly.

**What it means:** A non-critical dependency has been unhealthy for a while; the pod is still
serving traffic correctly, but the situation hasn't self-resolved.

**First checks:** Same as `mrag-unready` above — read `/ready`'s dependency detail to identify
which non-critical role is unhealthy.

**Action:** Investigate and restore at normal priority — this is a warning, not a page-now
incident, but a `DEGRADED` state that persists indefinitely tends to eventually cascade into
`UNREADY` (e.g., a degraded `retriever` leg that never recovers, combined with a later `indexer`
issue, would trigger the "both indexer and retriever unhealthy" `UNREADY` escalation).

**Do NOT:** let this sit unaddressed for days just because it isn't paging — it is the leading
indicator for the next tier's alert.

---

## mrag-cost-budget

**Alert:** `MRAGCostBudgetExceeded` — projected daily generation cost exceeds the configured
threshold.

**What it means:** Either genuine traffic growth, a runaway retry loop, or an unexpectedly
expensive model got selected.

**First checks:**
1. Break down `mrag.generation.cost_usd` by `model` — did a manifest change select a more
   expensive model than intended?
2. Check `mrag.generation.tokens` for an unusual spike in `output` tokens per request (e.g. a
   prompt change that produces much longer answers).
3. Check request *volume* (`mrag.request.duration_ms`'s count) — is this cost growth proportional
   to legitimate traffic growth, or concentrated in a short burst (possible retry storm/abuse)?

**Action:** If a model change is the cause and unintended, revert it. If it's a retry
storm, investigate the retry source. If it's genuine, legitimate growth, this is a budget
conversation, not an incident.

**Do NOT:** treat the $100/day figure in `alerts.yaml` as validated — replace it with your actual
approved budget before relying on this alert (see `slo.md` §5's own caveat).

---

## mrag-review-backlog

**Inactive reference signal:** no `MRAGReviewQueueBacklog` rule is shipped. The gauge is sampled on
enqueue but not on resolution, so it can report an obsolete high-water value rather than the live
queue depth.

**What it means:** Answers are being flagged for review (low-confidence answers, per
`HumanReviewGate`'s current, honest trigger scope — see that class's own docstring on what
actually sets `Answer.confidence` today) faster than reviewers are resolving them.

**First checks:**
1. Check whether `mrag.review.enqueued`'s rate spiked recently (a generation-quality regression
   flagging more answers) versus reviewer throughput simply not keeping up with a steady rate.
2. Check `HumanReviewGate.threshold` — was it recently lowered, flagging more answers than
   intended?

**Action:** If a quality regression is the cause, investigate the generator/prompt. If it's a
capacity issue, add reviewer capacity or temporarily raise the threshold (a product/risk decision,
not a purely technical one — do not make this change unilaterally without the same authorization
this codebase's own task discipline requires for security-policy-adjacent changes).

**Do NOT:** silently clear the queue without review — every item exists because a real answer was
judged too low-confidence to ship without a human check.

---

## mrag-index-divergence

**Alert:** `MRAGIndexDivergenceDetected` — the most recent `IndexReconciler.check()` run found a
divergence.

**What it means:** The lifecycle ledger's expected chunk ids don't match what the vector store
and/or lexical retriever actually hold — see `orchestration/reconciliation.py`'s own module
docstring for the mechanisms that can cause this (a crash between the ledger write and the index
write, a caller bypassing `RAGEngine` and calling `Container.indexer.delete()` directly, a restore
from an out-of-sync backup).

**First checks:**
1. Read the `type` label: `missing_in_vector`/`missing_in_lexical` (a chunk the ledger expects is
   absent from that store) versus `orphaned_in_vector`/`orphaned_in_lexical` (a chunk present in a
   store that no active document expects).
2. Check recent ingestion logs for `engine.ingest_lexical_failed_dense_not_rolled_back` (a known,
   already-logged failure mode — see `RAGEngine.ingest_chunks()`'s own extensive comment on why
   this isn't auto-rolled-back).

**Action:** Orphans are safely auto-repairable — `mrag reconcile --manifest <path> --mode repair`
(wraps `IndexReconciler.repair()`) deletes them outright. Missing ids are **not** auto-repaired
(`RepairResult.unresolved_missing`, printed by `mrag reconcile`'s own check output) — there is no
CLI command for this specific repair; re-ingest the affected document from its original source,
either via `mrag ingest` (if it's not currently tracked by a `lifecycle_ledger`) or by calling
`RAGEngine.rebuild_document(document)` directly (forces a full re-chunk/re-embed/re-index,
bypassing `ingest()`'s idempotency skip) if it already is.

**Do NOT:** run `repair()` as a reflexive first response without first reading which `type`
fired — orphan cleanup is safe and idempotent, but confirm you're not about to delete something
still legitimately in use before automating this in a broader remediation script.
