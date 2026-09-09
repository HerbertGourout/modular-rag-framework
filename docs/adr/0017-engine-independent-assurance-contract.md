# ADR-0017 — Engine-Independent Assurance Contract and Conformance Report

**Status:** Proposed — drafted 2026-09-09 as Lot 21's required focused contract ADR
(`docs/refactoring-plan.md`, `docs/refactoring/lot-21-engine-independent-assurance-contract.md`).
Not self-accepted. Acceptance, revision, or rejection is Herbert Gourout's decision, per
[`docs/refactoring/lot-0-baseline.md`](../refactoring/lot-0-baseline.md) §2's sole decision
authority — the same convention [ADR-0016](0016-provider-egress-control.md) followed for Lot 20.

**Date:** 2026-09-09.

**Authors:** Drafted by Claude Code, at explicit user instruction, before any Lot 21
implementation — per this repository's own rule that public-contract/structural changes get an
ADR *before* code, not after (the corrective posture Codex review pass 1's HIGH-004 finding
forced onto Lot 20, applied here from the start instead of retroactively).

---

## Context

[ADR-0015](0015-portable-assurance-and-external-application-boundary.md) (Accepted 2026-09-02)
authorized the *direction* — portable L0/L1/L2 assurance levels, an engine-independent
conformance report, and a future bring-your-own-application adoption path — but explicitly
deferred the concrete schema: "Exact names and schemas require a separate accepted contract ADR
before implementation" (§4), and "This decision approves the product and architecture direction,
not immediate implementation of its contracts" (closing line). `docs/architecture/
document-engine-contract.md`'s own "Planned assurance evolution" section repeats the same
deferral: "Exact types and enum values are deliberately absent here."

[ADR-0016](0016-provider-egress-control.md) (Accepted 2026-09-09) closed Lot 21's other
dependency — Lot 20's own sign-off. This ADR is the "separate accepted contract ADR" both of
those documents named as the remaining gate. It defines the public schema now, before any
implementation, rather than after — the ordering Codex review pass 1 (HIGH-004) had to correct
for Lot 20 is applied here from the start.

Full planned scope: [`lot-21-engine-independent-assurance-contract.md`](../refactoring/lot-21-engine-independent-assurance-contract.md).

### The gap this closes

Today, `contracts.engine.DocumentEngine` normalizes execution (`run`/`arun`/`astream`), results
(`EngineResult`), and a small set of generic capabilities (`EngineCapability`: streaming,
cancellation, tool use, multi-turn, governance intercept). It says nothing about *assurance* — a
caller cannot ask "did this engine actually enforce tenant isolation on this request?" or "is
this citation evidence something the framework verified, or just something the engine claimed?"
in a machine-readable, engine-neutral way. `orchestration/registry.py`'s LangGraph-unsupported-role
rejection list (`policy_engine`, `review_queue`, `audit_sink`, `feedback_sink`) is the closest
thing to this today, and it is binary (supported/rejected), not leveled, and not itself a public
contract a caller can introspect at runtime.

## Decision

### 1. New contract module: `contracts/assurance.py`

Vendor-neutral by construction, same discipline as `contracts/egress.py` (ADR-0016) and
`contracts/engine.py` itself — no LangGraph, OpenAI, Anthropic, or any other vendor name may
appear in this module's public signatures (CLAUDE.md §07). Imports only `core/`, per the
hexagonal layering rule every `contracts/` module follows.

### 2. Assurance levels — versioned, testable profiles

```python
class AssuranceLevel(StrEnum):
    L0 = "l0"  # opaque request/response
    L1 = "l1"  # evidence-aware
    L2 = "l2"  # governed stages
```

Matches [ADR-0015 §3](0015-portable-assurance-and-external-application-boundary.md)'s table
exactly — this ADR does not redefine what L0/L1/L2 *mean*, only how an adapter reports and proves
which one it achieves. `AssuranceLevel` is ordered (`L0 < L1 < L2`) for report comparisons, same
`_RANK`-dict pattern `core.enums.classification_rank()` (ADR-0016) already established for
`DataClassification` — reused here, not reinvented, per this project's own "extend, don't
rewrite" rule (CLAUDE.md §05).

### 3. Three-way evidence status — observable / verifiable / enforceable

The Lot 21 planning doc's required-scope item 3 names three concepts that must not collapse into
one boolean:

```python
class EvidenceStatus(StrEnum):
    UNSUPPORTED = "unsupported"    # the adapter does not produce this evidence at all
    OBSERVED = "observed"          # the adapter reports it; the framework did not independently check it
    VERIFIED = "verified"          # the framework independently validated the reported evidence
    ENFORCED = "enforced"          # the framework can block the stage on policy failure, not just observe it
```

Strictly ordered (`UNSUPPORTED < OBSERVED < VERIFIED < ENFORCED`) for the same reason
`AssuranceLevel` is: a conformance report needs to say "this adapter's tenant-filter evidence is
merely OBSERVED, not ENFORCED" without inventing a new comparison scheme per evidence kind.
`OBSERVED` without `VERIFIED` is the specific trap ADR-0015's own risk list named ("normalizing
evidence across engines can collapse meaningful vendor differences") — this contract makes that
distinction a first-class, testable field instead of an implicit assumption.

### 4. Normalized evidence catalog

The minimum useful set, per the Lot 21 planning doc's required-scope item 4, mapped onto types
that already exist in this codebase wherever one does — this ADR does not invent parallel
vocabulary for something already normalized elsewhere:

```python
class EvidenceKind(StrEnum):
    IDENTITY_TENANT = "identity_tenant"          # contracts.engine.ExecutionContext.tenant_id
    RETRIEVAL_PROVENANCE = "retrieval_provenance" # core.models.answer.Citation
    EGRESS_DECISION = "egress_decision"           # contracts.egress.EgressDecision (ADR-0016)
    POLICY_DECISION = "policy_decision"           # contracts.engine.GovernanceDecision
    AUDIT_COMPLETION = "audit_completion"         # contracts.audit.AuditEventType coverage
    USAGE_COST = "usage_cost"                     # generation token/cost metadata (ADR-0013)
    FEEDBACK_REVIEW_ROUTING = "feedback_review_routing"  # contracts.feedback, review queue
    STREAMING_PREVALIDATION = "streaming_prevalidation"  # pre-stream guard/policy check
```

Each `EvidenceKind` maps to an `EvidenceStatus` per adapter, per request or per adapter-declared
capability (see §6). This module does **not** redefine `EgressDecision`, `Citation`,
`AuditEventType`, or `GovernanceDecision` — it references their existing shapes. A conformance
report's `EGRESS_DECISION` entry, for example, is `VERIFIED` precisely when the framework's own
`EgressPolicy.check()` (ADR-0016) — not the adapter's self-report — produced the decision; on the
native engine this is always true today (`RAGEngine._enforce_egress()` calls it directly), and on
LangGraph it is true for the two checkpoints Lot 20's HIGH-002 fix added
(`LangGraphEngineAdapter._node_retrieve()`/`_node_generate()`).

### 5. Namespaced vendor metadata — extend the existing envelope, don't invent a new one

`EngineResult.metadata`/`ExecutionContext.extensions` (`contracts/engine.py`) already exist for
exactly this purpose (`docs/architecture/document-engine-contract.md`'s "Extension-envelope
discipline"). This ADR reuses that mechanism rather than adding a second one: vendor-specific
facts that cannot be normalized into an `EvidenceKind` stay in the existing namespaced envelope,
under the adapter's own key (e.g. `extensions["langgraph"]`), never flattened into a false common
denominator. No core control-plane logic may branch on envelope contents — same rule as today.

### 6. Conformance report shape

```python
@dataclass(frozen=True)
class EvidenceEntry:
    kind: EvidenceKind
    status: EvidenceStatus
    detail: str | None = None  # content-free, same discipline as EgressDecision.reason

@dataclass(frozen=True)
class ConformanceReport:
    adapter_name: str
    adapter_version: str
    achieved_level: AssuranceLevel
    evidence: tuple[EvidenceEntry, ...]
    contract_version: str = ASSURANCE_CONTRACT_VERSION
    schema_version: str = "1.0"
```

`achieved_level` is computed, not adapter-asserted: L2 requires every evidence kind relevant to a
governed stage (egress, policy, audit completion) to be at least `ENFORCED`; L1 requires
retrieval provenance and identity/tenant at least `VERIFIED`; L0 requires nothing beyond a
report existing at all. The exact per-level required-kind mapping is implementation detail for
the Lot 21 spike, not fixed by this ADR — what this ADR fixes is that the mapping must be a pure,
testable function from `evidence` to `achieved_level`, never a value the adapter sets directly
(an adapter claiming L2 while actually only observing evidence is exactly the overclaim Lot 21's
required-scope item 8 and acceptance-evidence list name as a mandatory negative test).

### 7. How an adapter reports this — additive to `DocumentEngine`, not a breaking change

Per `docs/architecture/document-engine-contract.md`'s own compatibility policy, adding a method to
`DocumentEngine` is a breaking Protocol change requiring an ADR — this is that ADR for exactly one
addition:

```python
class DocumentEngine(Protocol):
    ...  # existing run/arun/astream/capabilities/name/engine_version, unchanged

    def conformance_report(self, context: ExecutionContext) -> ConformanceReport:
        """Report this adapter's actually-achieved assurance level and evidence
        for the given execution context. Must reflect real, checked state — not
        a static per-adapter constant — since evidence status can depend on
        which optional governance roles a manifest actually wired."""
        ...
```

Both existing adapters (`NativeEngineAdapter`, `LangGraphEngineAdapter`) must implement this
before Lot 21 can be called complete — required-scope item 8. `NativeEngineAdapter`'s report is
expected to reach L2 wherever the manifest wires the corresponding governance role (it already
enforces tenant isolation, egress, and policy directly via `RAGEngine`); `LangGraphEngineAdapter`
is expected to report accurately lower where its own documented scope boundary (Lot 15: no
audit-event emission — see `.review/handoff.md`'s Lot 20 MEDIUM-001 deferral for the concrete,
already-observed instance of this) means it cannot claim `ENFORCED`/`VERIFIED` for a kind it does
not actually check. **A conformance report that under-claims is honest; one that over-claims is
the specific defect this contract exists to make impossible to ship silently.**

### 8. Manifest validation before startup

Extends the existing `orchestration/registry.py::runtime_manifest_errors()` pattern (the same
function ADR-0016 §2 extended for egress) — deliberately not a new validation entry point. A
manifest may declare a required minimum assurance level (exact field name/shape: Lot 21
implementation detail, not fixed here, but it follows the same "reads raw manifest config, never
constructs a domain-module object" rule `orchestration/` already follows for egress and tenant
checks). `wire()` fails before serving a single request if the selected engine's
`conformance_report()` cannot reach the declared minimum — the same fail-closed-before-traffic
discipline ADR-0016 established, not a new philosophy.

## Out of scope for this contract

- **Wrapping an arbitrary existing client application without rebuilding its graph** — that is
  Lot 22's job (`docs/refactoring/lot-22-external-application-adapters-and-conformance.md`),
  gated on this ADR's acceptance plus Lot 21's own evidence, not pre-authorized here.
- **New agent, tool, GraphRAG, or VLM execution behavior** — unrelated to assurance reporting;
  ADR-0005 §5.2's delegation boundary is unchanged.
- **Any regulatory-certification claim.** A `ConformanceReport` proves what this framework's own
  code observed/verified/enforced for one request against one manifest — it is not GDPR/HIPAA/
  PCI-DSS certification, the same non-goal `docs/architecture/data-classification-policy.md`
  already states for the egress contract.
- **Treating vendor trace metadata as verified merely because it was returned.** An adapter
  reporting `OBSERVED` for a kind it cannot independently check must never be silently upgraded
  to `VERIFIED` by report-generation code — this is the literal purpose of keeping the two states
  distinct (see §3).
- **Redefining what L0/L1/L2 *mean***. That table is ADR-0015 §3's decision; this ADR only makes
  it machine-checkable.

## Compatibility and lifecycle expectations

- `ASSURANCE_CONTRACT_VERSION` (new, starts at `"1.0"`) versions `ConformanceReport`'s shape,
  following the exact pattern `contracts.engine.CONTRACT_VERSION` already established — a new
  contract module gets its own version constant, not a shared one, so the two can evolve
  independently.
- `EvidenceKind` is additive-safe (a new kind is not breaking, mirroring `EngineCapability`'s own
  documented policy in `docs/architecture/document-engine-contract.md`); removing or renaming an
  existing value is breaking and requires a new ADR, same as `EngineCapability`.
- `DocumentEngine.conformance_report()` must be implemented by both shipped adapters before Lot 21
  is evidenced complete (required-scope item 8) — no adapter may ship without it once this ADR is
  accepted, matching the same deprecation-window discipline
  `docs/architecture/document-engine-contract.md` applies to every other `DocumentEngine` method.
- This ADR does not itself authorize Lot 22. Per `docs/refactoring-plan.md`'s dependency gate,
  Lot 22 needs Lot 21's actual conformance-report evidence (both adapters, real reports, real
  negative tests), not merely this ADR's acceptance.

## Relationship to prior decisions

- **ADR-0015** (Accepted): this ADR is the "separate accepted contract ADR" §4 explicitly deferred
  to. It does not revise ADR-0015's own L0/L1/L2 definitions, product statement, or two-adoption-
  paths decision — it makes §3's table testable.
- **ADR-0016** (Accepted): `EgressDecision` (Lot 20) is one of eight `EvidenceKind` entries this
  contract normalizes, referenced, not redefined. Lot 20's own MEDIUM-001 deferral (LangGraph
  egress decisions enforced but unaudited, per `.review/handoff.md`) is exactly the kind of gap a
  `ConformanceReport` should surface honestly (`EGRESS_DECISION: ENFORCED` for LangGraph, but
  `AUDIT_COMPLETION: OBSERVED` at best, not `ENFORCED`, for the same adapter) rather than leave
  implicit.
- **ADR-0007** (Accepted, layer boundaries): `contracts/assurance.py` follows the same
  `orchestration/` may-import-only-`core`+`contracts`+`orchestration` rule every other contract
  extension in this programme has followed — `conformance_report()`'s implementation lives in each
  adapter (`orchestration/native_engine.py`, `adapters/llms/langgraph_engine.py`), not in
  `contracts/` itself.
- **`docs/architecture/document-engine-contract.md`**: this ADR is the "new ADR" its own
  compatibility policy requires for adding a `DocumentEngine` method (§7 above) — that document
  should be updated to reflect the accepted addition once this ADR's disposition is decided, not
  before.
- **Lot 22** (planned): explicitly gated on this ADR's disposition plus Lot 21's own evidence, per
  `docs/refactoring-plan.md`.

## Consequences

### Positive

- Makes ADR-0015's L0/L1/L2 promise checkable instead of aspirational — a manifest, a caller, and
  a test suite can all ask the same machine-readable question ("what does this adapter actually
  guarantee for this request?") and get the same answer.
- Reuses every existing normalized type it can (`EgressDecision`, `Citation`, `AuditEventType`,
  `GovernanceDecision`) rather than inventing parallel vocabulary — smaller contract surface,
  fewer places for the native and LangGraph reports to silently drift apart.
- The three-way `EvidenceStatus` distinction directly prevents the specific overclaim risk
  ADR-0015's own Consequences section flagged ("normalizing evidence across engines can collapse
  meaningful vendor differences") from being silently reintroduced by a naive boolean.
- `conformance_report()`'s additive-only change to `DocumentEngine` preserves every existing
  caller — no breaking change to `run`/`arun`/`astream`/`capabilities`.

### Negative / risks

- **A new required method on every current and future `DocumentEngine` implementation.** Any
  future third adapter (a "managed cloud engine," per ADR-0015's target architecture diagram) must
  implement `conformance_report()` honestly from day one — this raises the bar for adding a new
  engine adapter, deliberately, since an adapter that cannot honestly report its own assurance
  level is exactly the kind ADR-0015 warned against admitting.
- **The achieved-level computation (§6) is nontrivial and adapter-agnostic by design** — getting
  the per-level required-`EvidenceKind` mapping wrong (too lenient) would let an adapter claim L2
  it does not deserve; too strict would make a genuinely well-governed adapter report a
  misleadingly low level. This is exactly why Lot 21's own acceptance evidence requires negative
  tests for capability overclaim before this contract can be considered proven, not merely
  defined.
- **This is a design-time contract, not itself a governance mechanism.** Accepting this ADR
  authorizes the schema; it does not by itself make any adapter more governed than it already is
  — a `ConformanceReport` can only report what `RAGEngine`/`LangGraphEngineAdapter` already do,
  same limitation ADR-0016 itself has (a contract decides *whether*/what to report, not *how well*
  the underlying enforcement works).

## Open decision

**This ADR's own Status (Proposed) is the primary open decision** — accept, revise, or reject is
Herbert Gourout's to make, per the same sole-decision-authority convention ADR-0016 followed.
Candidate revision points, named explicitly rather than silently pre-decided:

1. Whether `conformance_report()` takes `ExecutionContext` (per-request, as drafted above) or is
   adapter-level/manifest-level only (computed once at `wire()` time) — the per-request shape
   costs more to compute but can reflect a governance hook only present on some requests; the
   manifest-level shape is cheaper but coarser. This ADR proposes per-request; a coarser
   alternative is a legitimate revision.
2. The exact per-`AssuranceLevel` required-`EvidenceKind` mapping (§6) — deliberately left as
   "Lot 21 implementation detail, proven by negative tests" rather than fixed inline here, since
   getting it wrong is a testable-and-fixable implementation bug, not a contract-shape decision
   this ADR needs to pre-commit to.
3. Whether `EvidenceKind` needs an initial ninth value for something this draft's minimum-useful-
   set omitted — the Lot 21 planning doc calls its own list "the minimum useful set," not
   exhaustive.
