# ADR-0018 — Existing-Application Adapter Boundary and Control-Point Declaration

**Status:** Proposed — drafted 2026-09-16 as Lot 22's required focused contract ADR
(`docs/refactoring-plan.md` §5 Phase F, `docs/refactoring/lot-22-external-application-adapters-and-conformance.md`).
**Revised 2026-09-16** after Herbert Gourout's review of the first draft, which returned "revise
before acceptance, without changing its direction" and seven specific corrections; §2, §5, §6, §7
and the lifecycle rule are materially different from that draft, and three of its four open
decisions are now closed. Not self-accepted: acceptance is the sole decision authority's, per
[`docs/refactoring/lot-0-baseline.md`](../refactoring/lot-0-baseline.md) §2 — the same convention
[ADR-0016](0016-provider-egress-control.md) and [ADR-0017](0017-engine-independent-assurance-contract.md)
followed. No Lot 22 implementation may begin before acceptance.

**Date:** drafted 2026-09-16, revised 2026-09-16.

**Authors:** Drafted by Claude Code, at explicit user instruction, before any Lot 22
implementation — per this repository's own rule that public-contract and structural changes get
an ADR *before* code (CLAUDE.md §07), the ordering ADR-0017 applied from the start.

---

## Context

[ADR-0015](0015-portable-assurance-and-external-application-boundary.md) (Accepted 2026-09-02)
authorized two adoption paths, the second being "wrap an existing application without rebuilding
its graph," and deferred every concrete contract to a later focused ADR.
[ADR-0017](0017-engine-independent-assurance-contract.md) (Accepted 2026-09-10) then defined how
an adapter *reports* assurance: `AssuranceLevel`, `EvidenceStatus`, `EvidenceKind`,
`ConformanceReport`, and `DocumentEngine.conformance_report()`, with `achieved_level` computed
from evidence rather than asserted by the adapter.

Lot 22 is the pilot that tests the product thesis against a real, foreign application. Its
required scope item 2 calls for "a thin application-adapter interface that accepts framework
execution context and returns normalized result/evidence without exposing vendor-native types to
callers." That sentence is the contract this ADR fixes.

### The gap this closes

Both adapters shipped today — `NativeEngineAdapter` and `LangGraphEngineAdapter` — are
**framework-owned**. They construct their execution from the wired `Container`, so the framework
decides where every governed stage sits and can always place a control there. ADR-0017's evidence
model was written against that world, where the answer to "can this control be enforced?" is
determined by which manifest roles were wired.

A third-party application inverts this. Its graph, prompts, tools, checkpoints and deployment
belong to someone else and must not change (Lot 22 required scope item 3, non-goal 3). The
framework can only attach a control where the application *happens to expose a hook*. "Which
roles did the manifest wire?" is no longer the question; "where can this particular application
actually be intercepted?" is — and nothing in the current contracts can express that, let alone
prove it.

Without a contract for it, an adapter author faces exactly one tempting shortcut: declare
`EGRESS_DECISION: ENFORCED` because the framework *has* an egress policy, while the application
calls its model provider through a code path the adapter never sees. That report would be
syntactically valid under ADR-0017 and materially false. Lot 22's security requirements name this
class of failure four times over (items 3, 5, and the acceptance-evidence line "unsupported
controls are visible before deployment"). This ADR makes it structurally impossible to state
without a falsifiable claim behind it.

**Research grounding** (CLAUDE.md §05 rule 8): arXiv 2604.11623v3 (*Context Kubernetes*,
[DIGEST-architecture](../research/DIGEST-architecture.md)) supports three choices below — a
narrow, fixed-operation adapter interface decoupling orchestration from the thing adapted (their
CxRI, a near-isomorph of this repo's Protocol split); fail-closed behavior on control-plane
outage rather than degradation; and the invariant that delegated authority is contained by
granted authority, enforced at registration time rather than inferred at run time. Their own
stated open tension — that a probabilistic component can silently violate a governance guarantee —
is the direct argument for §3's rule that a control point must be a structural hook, never
something inferred from the application's behavior.

## Decision

### 1. No second execution port — `DocumentEngine` remains the boundary

An existing-application adapter implements the **existing** `contracts/engine.py::DocumentEngine`
Protocol. This ADR introduces no parallel execution port, no second `run`/`astream` surface, and
no alternative result envelope.

`DocumentEngine` already is "the delegation boundary itself": it is vendor-neutral by contract,
carries `ExecutionContext` inward and `EngineResult` outward, declares capabilities rather than
probing them, and since ADR-0017 reports conformance. A wrapped application is one more thing
behind that boundary, not a new kind of boundary. Introducing a second port would fork every
caller, every conformance suite and every governance path in two, for no capability the first port
lacks — precisely the "extend, don't rewrite" failure CLAUDE.md §05 rule 6 forbids.

What the existing port cannot express is *where the framework may intervene inside a foreign
application*. That, and only that, is what this ADR adds.

### 2. New contract module `contracts/application.py`, and how the framework reaches the profile

A new module, not an extension of `contracts/engine.py`: control-point declaration is meaningful
only for adapters that wrap something the framework does not own, and `engine.py` is on the
critical path of every request through both shipped adapters. Same discipline as
`contracts/egress.py` and `contracts/assurance.py` — imports only `core/`, and no vendor name
(LangChain, LangGraph, or any other) may appear in a public signature. A
`contracts/__init__.py` entry is required (`.claude/rules/contracts.md`).

A profile held privately inside an adapter is unreachable by the startup validation in §11, which
would make that validation unimplementable. The profile is therefore exposed through a narrow
introspection Protocol:

```python
@runtime_checkable
class ApplicationProfileProvider(Protocol):
    """Implemented *in addition to* `DocumentEngine` by an adapter that wraps an
    application the framework does not own. Introspection only: it executes
    nothing, and callers on the request path never use it."""

    @property
    def application_profile(self) -> ApplicationProfile: ...
```

This is **not** a second execution port. It has no run/stream surface, it is never called while
serving a request, and `DocumentEngine` is unchanged — no third method is added to a Protocol both
shipped adapters implement. An adapter that does not implement it is simply not an
existing-application adapter, and `runtime_manifest_errors()` says so by name rather than by
`AttributeError`.

The profile is a property of the integration, not of a request — which is why it is a plain
property here while ADR-0017's `conformance_report(context)` is per-request. *(Closes first-draft
open decision 1.)*

### 3. `ControlPoint` — where a control can attach

```python
class ControlPoint(StrEnum):
    REQUEST_ADMISSION = "request_admission"        # before the application receives the request
    RETRIEVAL_RESULT = "retrieval_result"          # the application's retrieved context/citations
    PRE_MODEL_EGRESS = "pre_model_egress"          # before content leaves for a model provider
    TOOL_INVOCATION = "tool_invocation"            # before a tool or nested model call
    STREAM_CHUNK = "stream_chunk"                  # before a streamed fragment reaches the caller
    RESULT_ADMISSION = "result_admission"          # after the application returns, before the caller sees it
```

**Only `REQUEST_ADMISSION` and `RESULT_ADMISSION` are structurally guaranteed**, because the
adapter owns the call itself: it runs before and after the application by construction. Every
other control point exists only if the application exposes a hook for it. This asymmetry is the
honest core of the external-application path and is stated in the contract rather than discovered
per pilot.

A control point is a **structural hook** — a callback, middleware, event, or interface the
application genuinely offers. It is never inferred from observed behavior, log parsing, or
heuristic detection of what the application appears to be doing (arXiv 2604.11623v3's own open
tension: a probabilistic signal cannot carry a governance guarantee).

### 4. `ControlPointSupport` — how firmly it attaches

```python
class ControlPointSupport(StrEnum):
    UNAVAILABLE = "unavailable"   # the application exposes no hook here
    OBSERVED = "observed"         # the adapter sees the event but cannot stop it
    ENFORCED = "enforced"         # the adapter runs before it proceeds, and can deny
```

Deliberately **not** `EvidenceStatus` reused. The two answer different questions: `EvidenceStatus`
grades a claim the framework makes about a request that ran; `ControlPointSupport` grades the
integration surface itself, independent of any request. `VERIFIED` has no meaning for an
attachment point, and a four-value enum with one meaningless member is an invitation to misuse.
The mapping between them is not left to prose — it is the normative table in §6.

Ordered `UNAVAILABLE < OBSERVED < ENFORCED`, same `_RANK`-dict pattern as
`classification_rank()` (ADR-0016) and `AssuranceLevel` (ADR-0017).

### 5. `ApplicationProfile` — total, not partial

```python
class EgressPathKind(StrEnum):
    MODEL = "model"                      # a completion/embedding/rerank call to a provider
    TOOL = "tool"                        # a tool or nested agent call that may itself reach a provider
    RETRIEVAL_BACKEND = "retrieval_backend"  # a vector/search backend the application calls itself

@dataclass(frozen=True)
class EgressPath:
    name: str                            # adapter-assigned, stable, content-free
    kind: EgressPathKind
    control_point: ControlPoint | None   # None: the adapter cannot attach to this path at all

@dataclass(frozen=True)
class ControlPointBinding:
    point: ControlPoint
    support: ControlPointSupport
    detail: str | None = None            # content-free, same discipline as EgressDecision.reason

@dataclass(frozen=True)
class ApplicationProfile:
    application_name: str
    application_version: str
    adapter_version: str
    configuration_fingerprint: str       # see below
    bindings: tuple[ControlPointBinding, ...]
    egress_paths: tuple[EgressPath, ...]
    schema_version: str = "1.0"
```

Four construction-time invariants, enforced in `__post_init__` so a malformed profile cannot
exist rather than being caught later by a reviewer:

1. **`bindings` is total and duplicate-free**: exactly one entry per `ControlPoint` member, no
   more, no fewer. A partial mapping would let an unconsidered control point disappear by
   omission, which is the same defect in a different place — the same reason `ConformanceReport`
   does not allow a kind to be silently absent.
2. **`REQUEST_ADMISSION` and `RESULT_ADMISSION` may never be `UNAVAILABLE`.** The adapter owns the
   call; declaring otherwise describes an adapter that does not exist. This is a contract
   violation, not a low score.
3. **`egress_paths` is a closed declaration.** Every provider-reaching path the adapter knows of is
   listed, each either bound to a control point or explicitly `None`. An empty tuple asserts the
   application reaches no provider at all — a strong claim, allowed, and one §7's isolation test
   is expected to falsify if untrue.
4. **`configuration_fingerprint` is mandatory, content-free, and reproducible**: a stable digest
   over the inputs that can change the profile — application and adapter versions, which hooks
   were enabled, and the deployed configuration that selects them. Two deployments producing
   different profiles must produce different fingerprints, and the same deployment must reproduce
   its own. It carries no secret, no endpoint and no tenant data. Lot 22's acceptance evidence
   requires the comparison to be reproducible; without this, a report cannot be tied to the
   configuration that produced it.

**`uncontrolled_egress` is computed, never declared.** The first draft made it a mandatory bool,
which is an unverifiable assertion about a negative. It is now a derived property:

```python
    @property
    def uncontrolled_egress(self) -> bool:
        """True when any declared provider-reaching path is not bound to a control
        point the adapter can actually block."""
```

— true when any `EgressPath` has `control_point is None`, or whose bound control point's support
is below `ENFORCED`. An author can no longer set it to `False` while listing an unbound model
path; the two statements are now the same statement. *(Closes first-draft open decision 2.)*

**The residual limit, stated rather than hidden**: this makes *declared* coverage computable. It
cannot prove the declaration is complete — an egress path nobody listed remains invisible to it.
That gap is closed by evidence, not by the type: §7's mandatory network-isolation test is what
makes an empty or short `egress_paths` falsifiable.

### 6. The normative mapping: control-point support caps evidence status

Each `EvidenceKind` (ADR-0017 §4) depends on specific control points. The **ceiling** below is the
highest `EvidenceStatus` the integration surface permits; the **final** status of an entry in a
`ConformanceReport` is:

```
final_status = min(status the framework actually earned per ADR-0017, ceiling from this table)
```

Both halves are required. A control point being `ENFORCED` never *grants* evidence — it only
stops capping it; the framework must still have genuinely run the check ADR-0017 describes.

| `EvidenceKind` | ≥ `OBSERVED` requires | ≥ `VERIFIED` requires | `ENFORCED` requires |
|---|---|---|---|
| `IDENTITY_TENANT` | `REQUEST_ADMISSION` ≥ `OBSERVED` | same (framework-owned, §8) | `REQUEST_ADMISSION` = `ENFORCED` |
| `RETRIEVAL_PROVENANCE` | `RESULT_ADMISSION` ≥ `OBSERVED` | `RETRIEVAL_RESULT` ≥ `OBSERVED` | `RETRIEVAL_RESULT` ≥ `OBSERVED` **and** `RESULT_ADMISSION` = `ENFORCED` |
| `EGRESS_DECISION` | `PRE_MODEL_EGRESS` ≥ `OBSERVED` | `PRE_MODEL_EGRESS` ≥ `OBSERVED` | every declared `MODEL` and provider-reaching `TOOL` path bound at `ENFORCED` — i.e. `uncontrolled_egress is False` |
| `POLICY_DECISION` | `REQUEST_ADMISSION` ≥ `OBSERVED` | same | `REQUEST_ADMISSION` = `ENFORCED` **and** `RESULT_ADMISSION` = `ENFORCED` |
| `AUDIT_COMPLETION` | `REQUEST_ADMISSION` **and** `RESULT_ADMISSION` ≥ `OBSERVED` | same | `RESULT_ADMISSION` = `ENFORCED` (a failed audit write fails the request) |
| `USAGE_COST` | `RESULT_ADMISSION` ≥ `OBSERVED` | `PRE_MODEL_EGRESS` = `ENFORCED` | **unreachable by construction** |
| `FEEDBACK_REVIEW_ROUTING` | `RESULT_ADMISSION` ≥ `OBSERVED` | same | `RESULT_ADMISSION` = `ENFORCED` |
| `STREAMING_PREVALIDATION` | `STREAM_CHUNK` ≥ `OBSERVED` | same | `STREAM_CHUNK` = `ENFORCED` |

Reading the table:

- **`UNAVAILABLE` forces `UNSUPPORTED`** for every kind that requires that point, since no row's
  `OBSERVED` requirement can be met.
- **`OBSERVED` permits `VERIFIED` but never `ENFORCED`.** Seeing an event is enough for the
  framework to check it independently; it is not enough to stop it. This distinction is the whole
  reason `EvidenceStatus` has four values.
- **`USAGE_COST` can never be `ENFORCED`**, whatever the profile: there is no stage to block. Cost
  is reported by the application (`OBSERVED`) or measured by a framework-owned model call
  (`VERIFIED`). A report claiming otherwise is malformed, not merely optimistic.
- **`STREAMING_PREVALIDATION` does not apply** when the adapter declares no
  `EngineCapability.STREAMING`; it is `UNSUPPORTED` and caps nothing, rather than dragging the
  level down for an unused capability.

Where a kind names several control points, the ceiling is the **minimum** across them — the
weakest attachment governs, never the strongest.

This table is normative and belongs in a test (`tests/contract/`), not only in this document. §5's
invariants make its inputs total, so the function computing a ceiling is pure and exhaustively
testable over the enum product.

### 7. Negative tests are a build gate, not a runtime inference

The first draft said a binding declared `ENFORCED` without a passing negative test "is treated as
`OBSERVED`". That is not implementable: at run time the adapter has no idea which CI tests
executed, and a report has no business guessing at the state of a test suite. The rule is
therefore moved to the only place that can enforce it:

- an adapter **declares** `ENFORCED` in its profile, and the runtime takes that declaration at
  face value — the profile is a static, reviewed artifact, not a runtime deduction;
- the **conformance suite** requires, for every binding declared `ENFORCED`, a corresponding
  negative test proving the control actually blocks: a denied request the application never
  receives, a blocked egress that never reaches the provider, a withheld stream fragment;
- a missing or failing negative test **fails the build**. It does not quietly lower a score.

An `ENFORCED` claim is therefore verified before shipping, by machinery that can actually see the
tests, and the runtime stays honest about what it can know. Additionally, every profile — including
one declaring `egress_paths=()` — requires a **network-isolation test** proving no undeclared
provider call escapes during a representative run; this is what makes §5's closed declaration
falsifiable rather than merely asserted. *(Closes first-draft open decision 4.)*

Reviewing these tests is the highest-value review work in Lot 22, and the easiest to do badly: a
test that exercises the adapter's own wrapper instead of the application's real bypass path proves
nothing while appearing to prove everything.

### 8. Identity and tenant are framework-owned, never application-supplied

`ExecutionContext.tenant_id`, `user_id` and `roles` are constructed by the framework from a
verified identity (`contracts/identity.py`, `adapters/auth/`) and passed *inward*. An
application-returned tenant, user, role or permission claim never overwrites them, and no
control-plane logic branches on one.

Application-returned identity metadata lands in the existing namespaced extension envelope
(ADR-0017 §5, `docs/architecture/document-engine-contract.md`'s extension-envelope discipline)
under the adapter's own key, where it is inert by contract. This is arXiv 2604.11623v3's
*authority containment* invariant, enforced at the boundary rather than trusted at run time: the
wrapped application's authority is contained by the authority the framework already established,
never the reverse.

### 9. Streaming: no fragment before the declared level's checks

An adapter declaring both `EngineCapability.STREAMING` and a level whose evidence requires a
pre-output check must bind `STREAM_CHUNK` at `ENFORCED`, or it may not declare that level — which
§6's table now enforces arithmetically rather than by exhortation. An application that streams
directly to its own caller, with no hook the adapter can place a check behind, is
`STREAM_CHUNK: UNAVAILABLE` — a correct and acceptable declaration that simply caps the level
(Lot 22 security requirement 4).

### 10. Fail-closed on control-plane unavailability

If a framework-owned control attached at an `ENFORCED` control point cannot execute — the egress
policy is unreachable, the guard raises, the identity context is absent — the adapter denies the
request. It does not proceed with the control skipped, and it does not silently downgrade its own
report to justify having proceeded. This is ADR-0016's established discipline and
arXiv 2604.11623v3's measured finding (fail-closed on Permission-Engine outage), applied at the
application boundary. A missing hook lowers the declared level *before* deployment; a failing
control denies *during* it. Neither is ever a silent allow.

### 11. Startup validation

Extends `orchestration/registry.py::runtime_manifest_errors()`, the same entry point ADR-0016 §2
and ADR-0017 §8 extended — not a new one. It reads the adapter's `ApplicationProfile` through §2's
provider Protocol, computes each `EvidenceKind`'s ceiling from §6's table, and rejects the
manifest before serving if the resulting maximum reachable level cannot meet
`assurance.min_level`. An adapter selected as an application adapter that does not implement
`ApplicationProfileProvider` is itself a manifest error, reported by name.

This gate is a *ceiling* check — it proves the integration surface could in principle support the
required level, not that any request achieved it. The existing `wire()`-time gate (ADR-0017 §9)
and its stated limit are unchanged: a structurally conformant no-op control passes a startup gate,
which is why §7's negative tests, not this gate, are what make an `ENFORCED` binding credible.

### 12. Where the adapter lives

`adapters/applications/`, one subpackage per wrapped application. Layering is unchanged and not
relaxed: `contracts/` + `core/` + the application's own SDK, never a domain module (ADR-0001,
enforced by `scripts/check_layering.py --strict`). The pilot application itself lives in its own
repository and is not vendored here; this repository holds the adapter, its fixtures and its
tests.

Per Lot 22 required-scope item 8, a second **reference fixture adapter** — a deliberately
minimal, fake application exercising a different control-point profile from the pilot's — ships
alongside the first. A contract demonstrated by exactly one implementation has not been
demonstrated to be general.

## Out of scope for this contract

- Supporting more than one wrapped application, or more than one version of its SDK, in Lot 22.
- Migrating the wrapped application toward the native engine, or rebuilding its graph from
  framework component factories — both are explicit Lot 22 non-goals.
- A general plugin marketplace, adapter registry, or third-party adapter distribution channel.
- Modifying the wrapped application's source to add hooks. If a control point needs one, that is
  recorded as measured integration cost against the native-tooling baseline (Lot 22 items 4 and 7),
  not performed silently and counted as framework capability.
- Pseudonymization, OPA behind `PolicyEngine`, and richer provider profiles — still open from
  ADR-0016, unchanged here.
- Any claim about the product thesis. This ADR defines the contract the pilot is measured
  *through*; the decision gate that follows the measurement is Lot 22's, and its outcome may be to
  stop.

## Compatibility and lifecycle expectations

- `contracts/application.py` is additive. No existing Protocol, dataclass or enum changes, so no
  conformance test for a shipped adapter breaks and neither shipped adapter is touched.
- **A new `ControlPoint` member never changes an existing profile's computed level.** §6's table
  is versioned with `ApplicationProfile.schema_version`; a new member participates in level
  computation only for profiles declaring the schema version that introduced it. Silently lowering
  a deployed integration's level because the contract grew a member would be exactly the kind of
  invisible compatibility break this project's own compatibility policy forbids — an existing
  profile keeps its meaning until its author deliberately migrates it. §5's totality invariant is
  checked against the member set of the profile's own declared schema version, so an older profile
  stays valid.
- Existing `ControlPoint`, `ControlPointSupport` and `EgressPathKind` members are never removed or
  renamed within a schema version.
- `adapters/applications/**` should be added to `.claude/settings.json`'s `ask` bucket alongside
  the other adapter directories, since it hosts a security-relevant boundary.

## Relationship to prior decisions

| Decision | Relationship |
|---|---|
| [ADR-0001](0001-modular-architecture.md) | Unchanged. The adapter obeys the same import rules as every other adapter. |
| [ADR-0005](0005-document-ai-control-plane-boundary.md) | Consistent: the wrapped application is a delegated execution engine; the framework owns governance and evidence around it. |
| [ADR-0015](0015-portable-assurance-and-external-application-boundary.md) | This is the focused contract ADR §4 deferred, for the second adoption path. |
| [ADR-0016](0016-provider-egress-control.md) | Reused unchanged. §5's `egress_paths` states where `EgressPolicy` provably cannot reach. |
| [ADR-0017](0017-engine-independent-assurance-contract.md) | Extended, not superseded. `achieved_level` stays computed; §6 adds a ceiling derived from the integration surface. |
| [ADR-0006](0006-external-engine-selection.md) | Distinct. ADR-0006 selected an engine the framework drives; this covers an application the framework does not drive. |

## Consequences

### Positive

- An overclaimed assurance level cannot reach production: an `ENFORCED` binding without a passing
  negative test fails the build. Honesty stops being a review-time judgment and becomes a gate.
- `uncontrolled_egress` can no longer contradict the paths declared beside it — they are one
  statement, computed, not two that a careless author can leave inconsistent.
- The report tells a deployment owner what is *not* covered, before deployment — the outcome
  Lot 22's acceptance evidence demands.
- Reusing `DocumentEngine` means the existing semantic conformance suite applies to a wrapped
  application on day one, with no parallel test matrix.
- §6's table is a pure function over total inputs, so the whole mapping is exhaustively testable
  rather than argued case by case.

### Negative / risks

- **A realistic pilot will score low.** A typical LangChain application exposes callbacks but not
  a blocking pre-egress hook, so the honest outcome may be L0/L1 with unbound egress paths. That
  is the contract working, and it may also be evidence against the product thesis — which is what
  Lot 22's decision gate is for. It must not be answered by loosening this contract.
- **`egress_paths` is only as complete as its author.** The isolation test in §7 is the real
  defense, and a weak one written against a permissive fixture would restore the exact blind spot
  the structure was introduced to remove.
- **`configuration_fingerprint` has no canonical definition here.** Two adapters could compute it
  over different inputs and both satisfy the wording. Lot 22 must pick one recipe and document it;
  until then the field is reproducible per adapter, not comparable across them.
- **`ControlPoint`'s six members are a guess** shaped by one unwritten pilot. The lifecycle rule
  now makes adding one safe rather than silently punitive, but the initial set should not be
  mistaken for a surveyed taxonomy.
- **Two evidence-shaped enums now exist** (`EvidenceStatus`, `ControlPointSupport`). The
  distinction in §4 is real but subtle; §6's table, held in a test, is the mitigation.
- **This ADR presumes the wrapped application is cooperative** — reachable, version-pinned, and
  willing to expose hooks. A hostile or frozen application is simply out of reach, and the
  contract says so by yielding `UNAVAILABLE` everywhere rather than by failing loudly.

## Open decisions

Three of the first draft's four open items are closed above: the profile is exposed through
`ApplicationProfileProvider` (§2), `uncontrolled_egress` is computed from declared egress paths
(§5), and a missing negative test fails the build rather than downgrading a runtime report (§7).
What remains genuinely open:

1. **The six initial `ControlPoint` members**, and the three `EgressPathKind` members beside them.
   Both sets are shaped by a pilot that has not been written. The lifecycle rule makes growth safe;
   it does not make the initial choice right.
2. **The `configuration_fingerprint` recipe** — which inputs, which digest, and whether it must be
   comparable across adapters or only reproducible within one. Drafted as reproducible-within-one;
   cross-adapter comparability is a stronger and more useful property if Lot 22 can define it
   without over-fitting to the first integration.
