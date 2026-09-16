# ADR-0018 — Existing-Application Adapter Boundary and Control-Point Declaration

**Status:** **Proposed.** Lot 22's required focused contract ADR (`docs/refactoring-plan.md` §5
Phase F, `docs/refactoring/lot-22-external-application-adapters-and-conformance.md`). **No Lot 22
implementation may begin until this ADR is accepted**, and acceptance is the sole decision
authority's per [`docs/refactoring/lot-0-baseline.md`](../refactoring/lot-0-baseline.md) §2 — the
same convention [ADR-0016](0016-provider-egress-control.md) and
[ADR-0017](0017-engine-independent-assurance-contract.md) followed. Nothing described below is
built: there is no `contracts/application.py`, no `adapters/applications/`, and no change to
`DocumentEngine`, `contracts/assurance.py` or `orchestration/registry.py` in this repository
today. Every code block here is a proposal.

**Date:** 2026-09-16.

**Authors:** Drafted by Claude Code, at explicit user instruction, before any Lot 22
implementation — per this repository's own rule that public-contract and structural changes get an
ADR *before* code (CLAUDE.md §07), the ordering ADR-0017 applied from the start. Revised the same
day after maintainer review.

---

## Context

[ADR-0015](0015-portable-assurance-and-external-application-boundary.md) (Accepted 2026-09-02)
authorized two adoption paths, the second being "wrap an existing application without rebuilding
its graph," and deferred every concrete contract to a later focused ADR.
[ADR-0017](0017-engine-independent-assurance-contract.md) (Accepted 2026-09-10) then defined how an
adapter *reports* assurance. Its implementation is what this ADR must fit into, so the shipped
shapes matter more than the ADR prose:

```python
# src/modular_rag/contracts/assurance.py — shipped, unchanged by this ADR
@dataclass(frozen=True)
class ConformanceReport:
    adapter_name: str
    adapter_version: str
    evidence: tuple[EvidenceEntry, ...]   # exactly one entry per EvidenceKind (__post_init__)
    contract_version: str = ASSURANCE_CONTRACT_VERSION
    schema_version: str = "1.0"

    @property
    def achieved_level(self) -> AssuranceLevel:
        return compute_achieved_level(self.evidence)   # pure function of evidence alone
```

Three properties of that module constrain everything below and are **not** modified by this ADR:
`achieved_level` is a computed property with no constructor path; `compute_achieved_level()` is a
pure function of the evidence tuple alone; and `evidence` is *total* — one entry per
`EvidenceKind`, enforced at construction, so a report cannot hide a kind by omitting it.

Lot 22 is the pilot that tests the product thesis against a real, foreign application. Its required
scope item 2 calls for "a thin application-adapter interface that accepts framework execution
context and returns normalized result/evidence without exposing vendor-native types to callers."
That sentence is the contract this ADR fixes.

### The gap this closes

Both adapters shipped today — `NativeEngineAdapter` and `LangGraphEngineAdapter` — are
**framework-owned**. They construct their execution from the wired `Container`, so the framework
decides where every governed stage sits and can always place a control there.
`orchestration/registry.py::_capability_evidence()` encodes exactly that assumption: it derives
what a wiring *could* claim from which manifest roles are present and structurally conformant.

A third-party application inverts it. Its graph, prompts, tools, checkpoints and deployment belong
to someone else and must not change (Lot 22 required scope item 3, non-goal 3). The framework can
only attach a control where the application *happens to expose a hook*. "Which roles did the
manifest wire?" is no longer sufficient; "where can this particular application actually be
intercepted?" is the question — and nothing in the current contracts can express it, so
`_capability_evidence()` would happily grant `EGRESS_DECISION: ENFORCED` to a manifest that wires
an `EgressPolicy` beside an application that reaches its provider through a code path the adapter
never sees. That report would be syntactically valid, would satisfy `compute_achieved_level()`, and
would be materially false. Lot 22's security requirements name this class of failure repeatedly
(items 3 and 5, and the acceptance line "unsupported controls are visible before deployment").

**Research grounding** (CLAUDE.md §05 rule 8): arXiv 2604.11623v3 (*Context Kubernetes*,
[DIGEST-architecture](../research/DIGEST-architecture.md)) supports three choices below — a narrow,
fixed-operation adapter interface decoupling orchestration from the thing adapted (their CxRI, a
near-isomorph of this repo's Protocol split); fail-closed behavior on control-plane outage rather
than degradation; and the invariant that delegated authority is contained by granted authority,
checked at registration rather than inferred at run time. Their own stated open tension — that a
probabilistic component can silently violate a governance guarantee — is the direct argument for
§3's rule that a control point must be a structural hook, never something inferred from observed
behavior.

## Decision

### 1. No second execution port — `DocumentEngine` remains the boundary

An existing-application adapter implements the **existing** `contracts/engine.py::DocumentEngine`
Protocol. This ADR proposes no parallel execution port, no second `run`/`arun`/`astream` surface,
and no alternative result envelope.

`DocumentEngine` already is "the delegation boundary itself": vendor-neutral by contract, carrying
`ExecutionContext` inward and `EngineResult` outward, declaring capabilities rather than probing
them, and since ADR-0017 reporting conformance. A wrapped application is one more thing behind that
boundary, not a new kind of boundary. A second port would fork every caller, every conformance
suite and every governance path in two, for no capability the first lacks — precisely the "extend,
don't rewrite" failure CLAUDE.md §05 rule 6 forbids.

What the existing port cannot express is *where the framework may intervene inside a foreign
application*. That, and only that, is what this ADR adds.

### 2. How the profile reaches the framework — both options, and the selection

The startup gate in §14 must read an adapter's control-point profile before any request is served.
Two designs can deliver that. Both were evaluated; one is proposed.

**Option A — add a method to `DocumentEngine`.**

```python
class DocumentEngine(Protocol):
    ...
    def application_profile(self) -> ApplicationProfile | None: ...   # NOT proposed
```

*For:* one port, one place to look; no `isinstance` branch at the call site. *Against:* it is a
breaking Protocol change under `docs/architecture/document-engine-contract.md`'s own compatibility
policy, forcing both shipped adapters and every fixture in
`tests/contract/test_engine_conformance.py` to implement a method that is meaningless for them —
they *are* the framework, so they have no foreign integration surface to describe. Returning
`None` from two of three implementations is the shape of a concept that does not belong on that
Protocol. It also puts an integration-time concern on the request-path port, inviting a future
caller to consult it per request.

**Option B — a narrow companion Protocol (proposed).**

```python
@runtime_checkable
class ApplicationProfileProvider(Protocol):
    """Implemented *in addition to* `DocumentEngine` by an adapter that wraps an
    application the framework does not own. Introspection only: it executes
    nothing, and no request-path caller consults it."""

    @property
    def application_profile(self) -> ApplicationProfile: ...
```

*For:* `DocumentEngine` is unchanged, so no shipped adapter, conformance fixture or caller moves;
the capability is discovered the same way this repository already discovers optional structure —
`isinstance()` against a `runtime_checkable` Protocol, the mechanism `registry.py` uses today for
`TenantPolicy`, `EgressPolicy`, `AuditSink` and (per ADR-0009) `VectorIndexer`; and an adapter
selected as an application adapter that does not implement it is a *named* startup error rather
than an `AttributeError` on the first request. *Against:* two Protocols must be implemented
together; a reviewer must know to look in a second module; and, as §14 sets out, the profile can
only be read once the adapter instance exists, which is later in startup than the two gates
ADR-0016 and ADR-0017 extended.

**Proposed: Option B.** The deciding argument is that Option A's cost falls on code that has
nothing to do with the feature — two framework-owned adapters and their fixtures — while Option
B's cost falls on the new adapters that actually have a profile to declare. Optional structure
discovered by `runtime_checkable` is an established pattern here, not a new one.

This is a design proposal, not an accepted decision; see "Decisions requiring human authority".

### 3. `ControlPoint` — where a control can attach

```python
class ControlPoint(StrEnum):
    REQUEST_ADMISSION = "request_admission"   # before the application receives the request
    RETRIEVAL_RESULT = "retrieval_result"     # the application's retrieved context/citations
    PRE_MODEL_EGRESS = "pre_model_egress"     # before content leaves for a model provider
    TOOL_INVOCATION = "tool_invocation"       # before a tool or nested model call
    STREAM_CHUNK = "stream_chunk"             # before a streamed fragment reaches the caller
    RESULT_ADMISSION = "result_admission"     # after the application returns, before the caller sees it
```

**Only `REQUEST_ADMISSION` and `RESULT_ADMISSION` are structurally guaranteed**, because the
adapter owns the call itself: it runs before and after the application by construction. Every other
control point exists only if the application exposes a hook. This asymmetry is the honest core of
the external-application path, stated in the contract rather than rediscovered per pilot.

A control point is a **structural hook** — a callback, middleware, event, or interface the
application genuinely offers. It is never inferred from observed behavior, log parsing, or
heuristic detection of what the application appears to be doing.

### 4. `ControlPointSupport` — how firmly it attaches

```python
class ControlPointSupport(StrEnum):
    UNAVAILABLE = "unavailable"   # the application exposes no hook here
    OBSERVED = "observed"         # the adapter sees the event but cannot stop it
    ENFORCED = "enforced"         # the adapter runs before it proceeds, and can deny
```

Deliberately **not** `EvidenceStatus` reused. The two answer different questions: `EvidenceStatus`
grades a claim about a request that ran; `ControlPointSupport` grades the integration surface,
independent of any request. `VERIFIED` has no meaning for an attachment point, and a four-value
enum with one meaningless member invites misuse. The relationship between the two is the table in
§6, plus three rules that hold for every kind:

- **`UNAVAILABLE` forces `UNSUPPORTED`.** No hook, no claim.
- **`OBSERVED` can never produce `ENFORCED`.** Seeing an event suffices for the framework to check
  it independently (`VERIFIED`); it never suffices to stop it.
- **`ENFORCED` permits `ENFORCED` only when behavioural conformance passes** (§9). Support is a
  *permission to claim*, never the claim itself.

Ordered `UNAVAILABLE < OBSERVED < ENFORCED`, via a `control_point_support_rank()` helper following
the `assurance_level_rank()`/`evidence_status_rank()`/`classification_rank()` pattern already
established.

### 5. `ApplicationProfile` — total bindings, closed egress world

```python
class EgressPathKind(StrEnum):
    MODEL = "model"                          # a completion/embedding/rerank call to a provider
    TOOL = "tool"                            # a tool or nested agent call that may reach a provider
    RETRIEVAL_BACKEND = "retrieval_backend"  # a vector/search backend the application calls itself

@dataclass(frozen=True)
class EgressPath:
    name: str                                # adapter-assigned, stable, content-free; unique in the profile
    kind: EgressPathKind
    control_point: ControlPoint | None       # None: the adapter cannot attach to this path at all
    support: ControlPointSupport             # THIS path's own attachment strength, not the point's

@dataclass(frozen=True)
class ControlPointBinding:
    point: ControlPoint
    support: ControlPointSupport
    detail: str | None = None                # content-free, same discipline as EgressDecision.reason

@dataclass(frozen=True)
class ExpectedAuditEvent:
    event_type: AuditEventType                # contracts.audit — referenced, not redefined
    mandatory: bool                           # mandatory: failing to persist it blocks the result

@dataclass(frozen=True)
class ApplicationProfile:
    application_name: str
    application_version: str
    adapter_version: str
    integration_fingerprint: str
    bindings: tuple[ControlPointBinding, ...]
    egress_paths: tuple[EgressPath, ...]
    expected_audit_events: tuple[ExpectedAuditEvent, ...]
    schema_version: str = "1.0"
```

Five construction-time invariants, enforced in `__post_init__` so a malformed profile cannot exist
— the same discipline `ConformanceReport.__post_init__` already applies to `evidence`:

1. **`bindings` is total and duplicate-free**: exactly one `ControlPointBinding` per `ControlPoint`
   member of the profile's own `schema_version`, no more, no fewer. Omission is the failure mode
   this closes; `ConformanceReport` rejects a missing `EvidenceKind` for the identical reason.
2. **`REQUEST_ADMISSION` and `RESULT_ADMISSION` are structurally present and never `UNAVAILABLE`.**
   The adapter owns the call; declaring otherwise describes an adapter that cannot exist. This is a
   contract violation, not a low score.
3. **`egress_paths` is a closed-world declaration with per-path support.** Every provider-reaching
   path the adapter knows of is listed under a name unique within the profile, each either bound to
   a control point or explicitly `None`, and each carrying **its own** `support`. A path's support
   may never exceed its control point's binding support (a hook that cannot block anything cannot
   block this path), and `control_point is None` forces `UNAVAILABLE`. An empty tuple asserts the
   application reaches no provider at all — permitted, and exactly what §9's isolation probe exists
   to falsify.

   Per-path support is what closes the sharing hole: two model calls attached through the same
   `PRE_MODEL_EGRESS` hook are two attachments, not one. A hook that genuinely intercepts the first
   and misses the second is declared `ENFORCED` on one path and `OBSERVED`/`UNAVAILABLE` on the
   other, and §9 requires a probe per *path*, not per binding — so the second path cannot inherit
   the first one's proof.
4. **`expected_audit_events` is a closed declaration, duplicate-free**, naming every
   `AuditEventType` this integration's declared capabilities and control points imply for a served
   request, each marked mandatory or optional. It is the denominator of the `AUDIT_COMPLETION`
   claim in §6: a claim can never cover an event the profile did not expect, and a smaller declared
   set yields a smaller, honest claim rather than a silent one. An empty tuple is permitted and
   caps `AUDIT_COMPLETION` at `OBSERVED` — there is no coverage to verify.
5. **`integration_fingerprint` is mandatory, content-free and reproducible**: a stable digest over
   the inputs that can change this profile — application version, adapter version, which hooks the
   deployment enabled, and the adapter configuration selecting them. Two deployments with different
   profiles must produce different fingerprints; one deployment must reproduce its own. It carries
   no secret, endpoint, credential or tenant data. Lot 22's acceptance evidence requires the paired
   comparison to be reproducible, and a report that cannot be tied to the configuration that
   produced it is not reproducible evidence.

**Uncontrolled egress is computed, never asserted.** A self-declared boolean is an unverifiable
claim about a negative, and can contradict the paths listed beside it. Instead:

```python
    @property
    def uncontrolled_egress(self) -> bool:
        """True when any declared egress path is not bound to a control point
        this profile can actually block."""

    @property
    def egress_ceiling(self) -> ControlPointSupport:
        """The weakest `EgressPath.support` across every declared path —
        UNAVAILABLE when any path is unbound. An empty declaration yields
        UNAVAILABLE: an application that provably reaches no provider has
        nothing to enforce, and must not earn an enforcement claim for that
        emptiness."""
```

`egress_ceiling` is the **minimum over per-path support**, not over the control points those paths
share, and with no carve-out by kind. Multiple providers, a nested model call behind a tool, and a
retrieval backend the application queries itself are each their own attachment, and **partial
coverage caps the claim at the weakest one**: an application whose main completion call is
`ENFORCED` while one tool reaches a second provider unbound yields `UNAVAILABLE`, hence
`EGRESS_DECISION: UNSUPPORTED`, hence no L2. Intercepting most egress is not intercepting egress.

**The residual limit, stated rather than hidden:** this makes *declared* coverage computable. It
cannot prove the declaration is complete — a path nobody listed stays invisible to the type. That
gap is closed by §9's mandatory isolation probe, not by the data structure.

### 6. Normative ceiling: control-point support caps evidence status

Every `EvidenceKind` an external application can affect has a deterministic ceiling. The **ceiling**
is the highest `EvidenceStatus` the integration surface permits; it never grants anything.

| `EvidenceKind` | ≥ `OBSERVED` requires | ≥ `VERIFIED` requires | `ENFORCED` requires |
|---|---|---|---|
| `IDENTITY_TENANT` | `REQUEST_ADMISSION` ≥ `OBSERVED` | `REQUEST_ADMISSION` = `ENFORCED` **and** `RETRIEVAL_RESULT` ≥ `OBSERVED` | the `VERIFIED` requirements **and** `RESULT_ADMISSION` = `ENFORCED` |
| `RETRIEVAL_PROVENANCE` | `RESULT_ADMISSION` ≥ `OBSERVED` | `RETRIEVAL_RESULT` ≥ `OBSERVED` | `RETRIEVAL_RESULT` ≥ `OBSERVED` **and** `RESULT_ADMISSION` = `ENFORCED` |
| `EGRESS_DECISION` | `egress_ceiling` ≥ `OBSERVED` | `egress_ceiling` ≥ `OBSERVED` | `egress_ceiling` = `ENFORCED` (§5 — every declared path) |
| `POLICY_DECISION` | `REQUEST_ADMISSION` ≥ `OBSERVED` | same | `REQUEST_ADMISSION` = `ENFORCED` **and** `RESULT_ADMISSION` = `ENFORCED` |
| `AUDIT_COMPLETION` | `REQUEST_ADMISSION` **and** `RESULT_ADMISSION` ≥ `OBSERVED` | every event in the profile's **expected audit-event set** (below) is observable | the `VERIFIED` requirement **and** `RESULT_ADMISSION` = `ENFORCED`, so a failure to persist any *mandatory* event blocks the result |
| `USAGE_COST` | `RESULT_ADMISSION` ≥ `OBSERVED` | `egress_ceiling` = `ENFORCED` (the framework owns every model call, so it can measure rather than believe) | **unreachable by construction** |
| `FEEDBACK_REVIEW_ROUTING` | `RESULT_ADMISSION` ≥ `OBSERVED` | same | `RESULT_ADMISSION` = `ENFORCED` |
| `STREAMING_PREVALIDATION` | `STREAM_CHUNK` ≥ `OBSERVED` | same | `STREAM_CHUNK` = `ENFORCED` |

Reading it:

- Where a row names several control points, the ceiling is the **minimum** across them. The weakest
  attachment governs, never the strongest.
- **`IDENTITY_TENANT` deliberately requires more than admission.** Rejecting a request before the
  application sees it proves the adapter can *refuse*; it proves nothing about whether the foreign
  retriever honours the trusted tenant once the request is accepted. An application that takes a
  valid tenant-A context and then ignores it can still pass an admission check. So a claim above
  `OBSERVED` additionally requires visibility of what the application retrieved
  (`RETRIEVAL_RESULT`), and an enforcement claim requires the framework to be able to withhold the
  result (`RESULT_ADMISSION` = `ENFORCED`) when that content is out of tenant scope. §9 makes a
  two-tenant negative probe mandatory for any claim above `OBSERVED`; the existing missing-tenant
  admission probe may remain, but is not the isolation proof.
- **`AUDIT_COMPLETION` is about coverage, not about one final write.**
  `contracts/assurance.py` defines this kind as `AuditEventType` *coverage*, and ADR-0015's L2 row
  promises stage-level audit. A single fail-closed write at the end satisfies neither. The profile
  therefore declares an **expected audit-event set** — the events its declared capabilities and
  control points imply for a served request, each marked mandatory or optional — and the claim has
  two halves: every expected event is actually recorded for the request (`VERIFIED`), and failure
  to persist any mandatory one blocks release of the result (`ENFORCED`). An application whose
  internal stages are opaque declares a smaller expected set and earns a correspondingly smaller
  claim, which is the honest outcome; it does not earn `ENFORCED` for the stages it cannot see.
- **`USAGE_COST` can never be `ENFORCED`**, whatever the profile: there is no stage to block. Cost
  is reported by the application (`OBSERVED`) or measured by a framework-owned model call
  (`VERIFIED`). This matches the shipped `_capability_evidence()`, which caps `USAGE_COST` at
  `OBSERVED` for both existing adapters.
- **`STREAMING_PREVALIDATION` is `UNSUPPORTED` and caps nothing** when the adapter does not declare
  `EngineCapability.STREAMING`. Neither it nor `USAGE_COST` appears in any level's requirements in
  the shipped `_LEVEL_REQUIREMENTS`, so neither can lower a level on its own; they are reported for
  honesty, not for scoring.

This table is normative and belongs in `tests/contract/`, not only in this document. §5's totality
invariant makes its inputs total, so the ceiling function is pure and exhaustively testable over
the enum product.

### 7. How the ceiling combines with per-request evidence

`compute_achieved_level()` is **unchanged**. It remains a pure function of the final evidence tuple
alone, with no knowledge of profiles, adapters or control points. The ceiling applies *earlier*, to
each entry, before the tuple is built:

```
for each EvidenceKind:
    final_status = min( status the framework actually earned for this request,
                        ceiling(kind, profile) )

achieved_level = compute_achieved_level(tuple of final entries)   # ADR-0017, untouched
```

Both halves are required, and neither substitutes for the other. A control point at `ENFORCED`
never *grants* evidence — it only stops capping it; the framework must still have genuinely run the
check ADR-0017 describes, exactly as it does for the two shipped adapters. Conversely, evidence
genuinely earned is still capped when the surface could not support it, which is the case that does
not arise for framework-owned adapters and is the whole reason this ADR exists.

This keeps `achieved_level` computed only from normalized evidence, and keeps the capping rule in
one auditable place rather than distributed through an adapter's reporting code.

### 8. Three separate concepts, already separated in this repository

Lot 21's own review history forced this separation (`registry.py`'s `_wired_capability_evidence()`
docstring, Codex pass 1 HIGH-002 and pass 2 HIGH-002, recorded as an accepted risk in ADR-0017 §9).
This ADR adopts it rather than inventing a parallel scheme, and adds the profile to the first
concept only:

| Concept | Question it answers | Where it lives | What it cannot prove |
|---|---|---|---|
| **Startup capability** | May this deployment be *allowed to declare* `assurance.min_level: X`? | `runtime_manifest_errors()` (manifest-only, advisory) then `wire()` (constructed components, authoritative) — plus the profile ceiling, §14 | That any control actually enforces anything. `runtime_checkable` validates method presence, never behaviour. |
| **Behavioural conformance** | Does a denied control demonstrably stop a request? | `tests/contract/test_engine_conformance.py::assert_claims_match_behaviour()` — build/release time | That a specific production request was governed. |
| **Per-request evidence** | What was actually true for *this* request? | `DocumentEngine.conformance_report(context)` | Anything about a request that has not run. |

A startup structural check is never presented as proof of enforcement, in this document or in any
implementation of it.

### 9. Behavioural conformance is the gate for every `ENFORCED` claim

The mechanism already exists and must be extended, not duplicated.
`tests/contract/test_engine_conformance.py` holds a status-aware probe per evidence kind and
applies one rule: *for every kind a report claims above `UNSUPPORTED`, the suite must own a
behavioural probe for that kind at that strength, and that probe — plus every weaker one defined
for the kind — must pass. A claim with no probe, or with no probe at the claimed strength, is
itself a conformance failure.* Its `ENFORCED` rung already requires that "a denied or failing
control actually stops the request".

Lot 22 extends that harness along four axes. Each is a **per-attachment** obligation: a probe
proves the thing it exercises and nothing adjacent to it.

1. **A probe per `ENFORCED` binding.** For each `ControlPointBinding` declared `ENFORCED`, a probe
   must demonstrate a real block at that point: a denied request the application never receives, a
   stream fragment never emitted, a tool call that does not proceed. A missing or failing probe
   **rejects the conformance claim** — the profile is not certifiable, so the adapter cannot be
   delivered claiming that binding.
2. **A probe per declared egress *path*, not per binding.** For every `EgressPath` whose `support`
   is above `UNAVAILABLE`, a probe must show that *that specific path* is intercepted: at
   `ENFORCED`, the named provider is not reached when policy denies; at `OBSERVED`, the call is
   genuinely seen. Two paths sharing one `PRE_MODEL_EGRESS` hook require two probes, because one
   hook intercepting one path is not evidence about the other. A path with no probe at its declared
   strength rejects the claim.
3. **A two-tenant probe, mandatory for any `IDENTITY_TENANT` claim above `OBSERVED`.** Two tenants
   with disjoint corpora; a request carrying tenant A's verified context must not return tenant B's
   content, and at `ENFORCED` the framework must withhold the result rather than merely record the
   leak. The existing missing-tenant admission probe
   (`tests/contract/test_engine_conformance.py`'s `identity_enforced()`, which denies a request
   with `tenant_id=None`) may remain, but it proves admission, not isolation, and may not stand in
   for this.
4. **Audit-coverage probes, for any `AUDIT_COMPLETION` claim above `OBSERVED`.** One probe showing
   every event in the profile's `expected_audit_events` is recorded for a served request, and one
   missing-event probe per mandatory entry showing that failing to persist it blocks the result. A
   single final sink-failure probe is not sufficient.

Independently of all four, **a closed-world isolation probe is mandatory for every profile**,
including one declaring `egress_paths=()`: a representative run under network isolation must
produce no provider call the profile did not declare. It detects *undeclared* attachments and is
never a substitute for the per-path proof in axis 2 — a representative scenario that happens not to
exercise a second declared path proves nothing about it.

**No runtime code ever inspects the test suite.** An adapter declares its profile; the runtime
takes that declaration at face value, because a running process cannot know which tests executed
and a report that guessed would be worse than one that did not. The claim is rejected *before*
shipping, by machinery that can actually see the probes. This is a delivery gate, not a runtime
inference — a distinction the first draft of this ADR got wrong.

Reviewing these probes is the highest-value review work in Lot 22, and the easiest to do badly: a
probe that exercises the adapter's own wrapper instead of the application's real bypass path proves
nothing while appearing to prove everything.

### 10. Identity and tenant are framework-owned, never application-supplied

`ExecutionContext.tenant_id`, `user_id` and `roles` are constructed by the framework from a verified
identity (`contracts/identity.py`, `adapters/auth/`) and passed *inward*. An application-returned
tenant, user, role or permission claim never overwrites them, and no control-plane logic branches on
one.

Application-returned identity metadata lands in the existing namespaced extension envelope
(ADR-0017 §5, `docs/architecture/document-engine-contract.md`'s extension-envelope discipline) under
the adapter's own key, where it is inert by contract. This is arXiv 2604.11623v3's *authority
containment* invariant enforced at the boundary rather than trusted at run time: the wrapped
application's authority is contained by the authority the framework already established, never the
reverse.

### 11. Streaming: no fragment before the declared checks

An adapter declaring `EngineCapability.STREAMING` and claiming `STREAMING_PREVALIDATION` above
`UNSUPPORTED` must bind `STREAM_CHUNK` accordingly (§6), and may claim `ENFORCED` only with a probe
showing a fragment genuinely withheld (§9). An application that streams directly to its own caller,
with no hook behind which the adapter can place a check, is `STREAM_CHUNK: UNAVAILABLE` — a correct
declaration that caps that kind at `UNSUPPORTED` (Lot 22 security requirement 4).

No shipped level currently requires `STREAMING_PREVALIDATION`, so this caps a reported kind without
lowering a level. That is a property of today's `_LEVEL_REQUIREMENTS`, not a licence to stream
unchecked content: a declared `EngineCapability.STREAMING` with content emitted before the checks an
adapter claims elsewhere is a conformance failure under §9 regardless of level.

### 12. Fail-closed on control unavailability

If a framework-owned control attached at an `ENFORCED` control point cannot execute — the egress
policy is unreachable, the guard raises, the identity context is absent — the adapter denies the
request. It does not proceed with the control skipped, and it does not downgrade its own report to
justify having proceeded. This is ADR-0016's established discipline and arXiv 2604.11623v3's
measured finding (fail-closed on Permission-Engine outage), applied at the application boundary.

A missing hook lowers the declared ceiling *before* deployment; a failing control denies *during*
it. Neither is ever a silent allow, and neither may be weakened to help a pilot reach a higher
level.

### 13. Where the adapter would live

`adapters/applications/`, one subpackage per wrapped application. Layering is unchanged and not
relaxed: `contracts/` + `core/` + the application's own SDK, never a domain module (ADR-0001,
enforced by `scripts/check_layering.py --strict`). No vendor-native type appears in any public
signature proposed by this ADR.

The application keeps its graph, state, prompts, tools, checkpoints and deployment. None of that
ownership transfers to the framework; the pilot application lives in its own repository and is not
vendored here. This repository would hold the adapter, its fixtures and its probes.

Per Lot 22 required-scope item 8, a second **reference fixture adapter** — a deliberately minimal,
fake application with a different control-point profile from the pilot's — ships alongside the
first. A contract demonstrated by exactly one implementation has not been demonstrated to be
general.

### 14. Startup validation — and where the profile can actually be read

Startup already has two assurance gates, and **neither of them can see an `ApplicationProfile`**.
This is a structural fact of the current bootstrap sequence, not a detail to be waved at:

```
resolve_manifest(path)
  -> runtime_manifest_errors(manifest)        # manifest fields only; nothing constructed
  -> registry.wire(manifest)                  # builds Container components; no engine adapter yet
  -> load_engine(path) constructs the adapter # app/bootstrap.py — FIRST point an instance exists
  -> ApplicationService(...) serves requests
```

`runtime_manifest_errors()` takes a `PipelineManifest` and nothing else. `wire()` returns a
`Container` of components; the engine adapter is constructed afterwards, in
`app/bootstrap.py::load_engine()`. An earlier draft of this ADR placed the profile gate in the
first two, which is not implementable. The gate is therefore split across what each stage can
honestly check:

| Stage | What it can check about an application adapter | Strength |
|---|---|---|
| `runtime_manifest_errors(manifest)` | that `engine.adapter` names a known application adapter (see the construction boundary below), and that any manifest fields it requires are present | advisory, same status as `_declared_capability_evidence()` — necessary, not sufficient |
| `registry.wire(manifest)` | unchanged; the `Container`-level `assurance.min_level` gate keeps its existing meaning | authoritative for wiring, blind to the profile |
| `load_engine()` / `load_application()` | **the profile gate** | authoritative for the ceiling |

At the third stage, once the adapter instance exists and before it is returned to any caller:

1. resolve the adapter's `ApplicationProfile` through §2's provider Protocol, and raise a named
   `ConfigurationError` if an adapter selected as an application adapter does not implement it;
2. compute each `EvidenceKind`'s ceiling from §6;
3. cap the `_capability_evidence()` profile `wire()` already computed by those ceilings;
4. refuse to return the engine if the capped result cannot reach `assurance.min_level`.

`load_engine()` and `load_application()` are the only bootstrap entry points that select a
non-native adapter; `load_pipeline()` and `load_native_engine()` construct the native engine
directly and can never yield an application adapter, so they need no profile gate.

**The construction boundary, decided narrowly.** The gate above presumes the adapter instance
exists, and nothing in this repository can currently produce one: `app/bootstrap.py` hard-codes
`native` and `langgraph` in an `if`/`elif` chain, and `ComponentRegistry` registers *components*
by `(role, type_name)`, never `DocumentEngine` factories. Leaving this undecided would let Lot 22's
implementer pick a hard-coded branch, a repurposed component registry, or a new plugin registry —
three materially different architectures with different validation behaviour.

*Proposed, deliberately minimal:* **one explicit branch in the composition root**, beside the two
that exist, naming the single pilot adapter. It is the smallest change that makes the gate
reachable; it keeps `ComponentRegistry` unpolluted by engine adapters; and it makes adding a second
application adapter a visible, reviewed edit rather than a configuration act — appropriate while
the product thesis is still a hypothesis under test. A general engine-adapter factory registry with
its own manifest identifier and ownership rules stays **out of scope**, along with marketplace and
distribution concerns; if the pilot succeeds and a second adapter is justified, that registry is
its own ADR. *Alternative, for the record:* define that factory registry now, which avoids a later
migration but builds plugin infrastructure before a single pilot has shown the contract is worth
generalizing.

Refusing at stage three is still **before any request is served**, which is the fail-closed
property ADR-0016 established and the one that matters; it is simply later than the two gates
ADR-0016 §2 and ADR-0017 §8 extended. Lot 22 must not "fix" this by making
`runtime_manifest_errors()` construct an adapter: a manifest-validation function that instantiates
components would be a materially different and far more invasive contract, and `mrag validate` is
a dry run by definition.

This remains a **ceiling** check. It proves the integration surface could in principle support the
required level, never that any request achieved it or that any control enforces anything.
ADR-0017 §9's stated limit is inherited unchanged — a structurally conformant no-op control still
passes a startup gate, which is why §9's probes, not this gate, are what make an `ENFORCED` binding
credible.

## Out of scope for this contract

- Any Python implementation, including `contracts/application.py` itself.
- Changes to `DocumentEngine`, `contracts/assurance.py`, `orchestration/registry.py`, manifests or
  shipped adapters.
- Selecting or integrating the real pilot application; running the Lot 22 benchmark.
- Supporting more than one wrapped application, or more than one version of its SDK, in Lot 22.
- Migrating the wrapped application toward the native engine, or rebuilding its graph from framework
  component factories — both explicit Lot 22 non-goals.
- A general plugin marketplace, adapter registry, or third-party adapter distribution channel.
- Modifying the wrapped application's source to add hooks. If a control point needs one, that is
  recorded as measured integration cost against the native-tooling baseline (Lot 22 items 4 and 7),
  never performed silently and counted as framework capability.
- Pseudonymization, OPA behind `PolicyEngine`, and richer provider profiles — still open from
  ADR-0016, unchanged here.
- Any claim about the product thesis. This ADR defines the contract the pilot is measured *through*;
  the decision gate that follows the measurement is Lot 22's, and its outcome may be to stop.

## Compatibility and lifecycle expectations

- `contracts/application.py` would be purely additive. No existing Protocol, dataclass or enum
  changes, so no conformance test for a shipped adapter breaks and neither shipped adapter moves.
- **Adding a `ControlPoint` member must not lower an existing profile's assurance level.** §6's
  ceiling table is versioned with `ApplicationProfile.schema_version`; a new member participates in
  ceiling computation only for profiles declaring the schema version that introduced it, and §5's
  totality invariant is checked against that same version's member set. A deployed profile keeps
  its meaning until its author deliberately migrates it. Lowering a level therefore requires an
  explicit contract/schema evolution that changes the normative mapping — never the mere growth of
  an enum.
- Existing `ControlPoint`, `ControlPointSupport` and `EgressPathKind` members are never removed or
  renamed within a schema version.
- `adapters/applications/**` would need adding to `.claude/settings.json`'s `ask` bucket alongside
  the other adapter directories, since it hosts a security-relevant boundary.

## Relationship to prior decisions

| Decision | Relationship |
|---|---|
| [ADR-0001](0001-modular-architecture.md) | Unchanged. The adapter obeys the same import rules as every other adapter. |
| [ADR-0005](0005-document-ai-control-plane-boundary.md) | Consistent: the wrapped application is a delegated execution engine; the framework owns governance and evidence around it. |
| [ADR-0015](0015-portable-assurance-and-external-application-boundary.md) | This is the focused contract ADR §4 deferred, for the second adoption path. |
| [ADR-0016](0016-provider-egress-control.md) | Reused unchanged. §5's `egress_paths` states where `EgressPolicy` provably cannot reach. |
| [ADR-0017](0017-engine-independent-assurance-contract.md) | Extended, not superseded. `compute_achieved_level()` and `ConformanceReport` are untouched; §6 adds a ceiling applied to entries before the level is computed. ADR-0017 §9's stated limit on startup gates is inherited verbatim. |
| [ADR-0006](0006-external-engine-selection.md) | Distinct. ADR-0006 selected an engine the framework drives; this covers an application the framework does not drive. |

## Consequences

### Positive

- An overclaimed level cannot be delivered: an `ENFORCED` binding without a passing probe rejects
  the conformance claim at build time, through the harness that already enforces this rule for
  evidence kinds.
- Uncontrolled egress can no longer contradict the paths declared beside it — they are one computed
  statement, and partial coverage caps at the weakest path rather than averaging.
- Startup capability, behavioural conformance and per-request evidence stay three distinct
  concepts, matching the separation Lot 21's own reviews already forced.
- `compute_achieved_level()` is untouched, so ADR-0017's guarantee that a level is a pure function
  of normalized evidence survives intact.
- The report tells a deployment owner what is *not* covered, before deployment — Lot 22's
  acceptance evidence demands exactly that.
- Reusing `DocumentEngine` means the existing semantic conformance suite applies to a wrapped
  application on day one, with no parallel test matrix.

### Negative / risks

- **A realistic pilot will score low.** A typical LangChain application exposes callbacks but not a
  blocking pre-egress hook, so the honest outcome may be L0/L1 with unbound egress paths. That is
  the contract working. It may also be evidence against the product thesis — which is what Lot 22's
  decision gate is for, and it must not be answered by loosening this contract.
- **`egress_paths` is only as complete as its author.** §9's isolation probe is the real defense,
  and a weak one written against a permissive fixture would restore the exact blind spot the
  structure was introduced to remove.
- **The probe requirement multiplies Lot 22's test surface, and §9's per-attachment rule multiplies
  it again.** Every `ENFORCED` binding, every declared egress path above `UNAVAILABLE`, every
  mandatory expected audit event, and a two-tenant corpus each need a genuine probe against a
  foreign application — harder than probing framework-owned code. This is the deliberate price of
  refusing to let one probe certify several attachments, and Lot 22's 3–5 week time-box should be
  read with it in mind. If the burden proves unworkable, the correct response is a smaller declared
  profile with honestly lower claims, never a weaker probe rule.
- **`integration_fingerprint` has no canonical recipe here.** Two adapters could compute it over
  different inputs and both satisfy the wording; see below.
- **`ControlPoint`'s six members are a judgement made ahead of the evidence.** The lifecycle rule
  makes growth safe rather than silently punitive, but the initial set is not a surveyed taxonomy.
- **Two support-shaped enums now exist** (`EvidenceStatus`, `ControlPointSupport`). The distinction
  in §4 is real but subtle; §6's table, held in a test, is the mitigation.
- **This ADR presumes a cooperative application** — reachable, version-pinned, willing to expose
  hooks. A hostile or frozen one is out of reach, and the contract says so by yielding `UNAVAILABLE`
  everywhere rather than failing loudly.

## Decisions requiring human authority

Acceptance of this ADR ratifies all of the above. Three points are called out because each is a
judgement made ahead of the evidence that would settle it, and each has a real alternative:

1. **Profile exposure (§2).** *Recommended:* a companion `ApplicationProfileProvider` Protocol,
   leaving `DocumentEngine` unchanged. *Alternative:* add `application_profile()` to
   `DocumentEngine`, accepting a breaking Protocol change and a meaningless method on both shipped
   adapters. The recommendation puts the cost on the new code rather than on existing code.
2. **Initial member sets (§3, §5).** *Recommended:* ship the six `ControlPoint` and three
   `EgressPathKind` members as drafted, relying on the lifecycle rule to make later growth safe.
   *Alternative:* defer the enums entirely until the pilot reveals what it needs, at the price of
   having no reviewable contract before implementation starts — which would defeat this ADR's
   purpose.
3. **`integration_fingerprint` recipe (§5).** *Recommended:* reproducible-within-one-adapter, with
   the inputs named in §5 and the digest left to Lot 22. *Alternative:* a canonical cross-adapter
   recipe, which is more useful for comparing pilots but risks over-fitting to the first
   integration. The weaker property is proposed because it cannot be wrong; the stronger one can be
   proposed later by Lot 22 without a contract break.
4. **Adapter construction boundary (§14).** *Recommended:* one explicit branch in the composition
   root for the single pilot adapter. *Alternative:* a general engine-adapter factory registry with
   a manifest identifier now. The recommendation keeps plugin infrastructure unbuilt until a pilot
   has shown the contract is worth generalizing, at the cost of a later migration if it is.

**This ADR is Proposed. Lot 22 implementation is blocked until a human accepts it.**
