# Data Classification Policy

**Status:** originally a Lot 11a deliverable (`docs/refactoring-plan.md` Phase C) — a
paper-and-fixture policy, not enforcement code, at the time it was written. **Updated here to
reflect that Lot 11b/11c/20 have since executed** (`docs/refactoring-plan.md`'s change log):
tenant-scoped enforcement (Lot 11b/11c) and classification-aware provider-egress control (Lot 20)
are both real and wired in today, as two separate, independently-optional mechanisms — see §2 for
the tenant split and the "Outbound-provider control" note below for egress.
`core.enums.DataClassification` is no longer pure vocabulary: `Document.classification`/
`Chunk.classification` carry it, `governance.egress_policy` reads it, and its own docstring in
the source now names those consumers directly. Conflating "tenant enforcement landed" with
"classification-level enforcement landed" was the exact kind of mistake this document used to
invite by treating both as one "Lot 11b" outcome — they were never the same piece of work; the
gap that left open (classification-level enforcement) is what Lot 20 closes for the
provider-egress boundary specifically, not for every consumer named in §1's handling-requirement
column (`PolicyEngine`/`TenantIsolationPolicy` still do not branch on classification — see §5).

This document exists because Lot 11b ("Propagate authenticated identity and tenant through
`ExecutionContext`; enforce fail-closed policy before indexing, retrieval, and generation") needed
a classification scheme to enforce *against*. `docs/refactoring-plan.md` named this as a blocking
dependency at the time ("Blocks 11b, since identity/tenant propagation needs the classification to
enforce against") — in the event, Lot 11b's actual delivered scope was the *tenant_id*
identity/enforcement side of that dependency, not a `DataClassification`-level enforcement
mechanism; see §2.

---

## 1. Classification levels

Four levels, each strictly more restrictive than the last. A document, chunk, or answer carries
exactly one level at a time — the *highest* level of any information it contains (a chunk mixing
public and confidential content is classified `confidential`, not split).

| Level | Definition | Example in this framework's own domain | Handling requirement (the *policy*, not necessarily classification-driven automation — see note below) |
|---|---|---|---|
| `public` | Safe for unauthenticated or any-tenant access; no confidentiality obligation | Published documentation, marketing material, open-source code comments | No guard required; may be cached/logged verbatim |
| `internal` | Safe within the organization/tenant, not for external release | Internal runbooks, non-customer-identifying internal metrics, this repository's own source code | Tenant-scoped retrieval; `BasicSecurityGuard` recommended |
| `confidential` | Business-sensitive or third-party data under a confidentiality obligation | Client contracts, unreleased campaign strategy, vendor pricing | Tenant-scoped retrieval mandatory; `PatternRedactor` on answers; audit evidence required |
| `restricted` | Regulated personal data or data whose exposure creates legal/compliance exposure | Any document containing an item from the PII/secret schema below (§3), health data, payment data | All of `confidential`, plus mandatory redaction before storage/logging/external calls, human review for low-confidence answers, narrowest-need-to-know tenant scoping |

**Important distinction, corrected in this pass:** the *controls* named in the right-hand column
above — tenant-scoped retrieval (`TenantIsolationPolicy`), `PatternRedactor`, audit evidence
(`AuditSink`), `HumanReviewGate` — are all real, shipped, and operational today (Lots 10, 11b,
11c). What is **not** real is any code path that reads a document's `DataClassification` level and
*automatically* turns the right controls on for you.

Nothing in this codebase currently sets or consumes a per-document classification value at
runtime — a manifest author must still choose to enable `governance.redactor`,
`governance.tenant_policy`, etc. by hand, the same way regardless of what classification level a
human might mentally assign the data. This table is the policy a deployment *should* follow,
worked out level by level; it is not yet a policy the system enforces for you based on a
classification field.

**Default when unclassified:** `restricted`, as a policy recommendation — an operator manually
configuring a deployment should default to the `restricted` handling requirements when a
document's classification hasn't been explicitly decided, matching the fail-closed spirit of
`PolicyEngine`'s own real, code-level default (a policy-engine error denies, never allows, by
default). This is a recommended human default, not something `DataClassification` itself causes
to happen automatically — see the distinction above.

**Outbound-provider control (Lot 20, mandatory for known remote providers):** `PatternRedactor`
still only processes answer text after generation and selected stored feedback/audit text — it
does not classify or block raw queries, retrieved chunks, documents, or embedding inputs before a
remote adapter call. Lot 20 closes that specific gap with a separate control:
`governance.egress_policy` (`security.policies.egress_policy.ManifestEgressPolicy`) checks
`Chunk.classification` (or, for query-time embedding at retrieval, the policy's own
`default_classification` — `Query` itself carries no classification field) against a
manifest-declared provider profile before `Embedder.embed()`, `Reranker.rerank()`, and
`Generator.generate()`. Not opt-in for this framework's own known remote provider types
(`openai`, `anthropic`, `openai-embeddings`) — a manifest wiring one with no covering
`governance.egress_policy` fails to load at all (Codex review pass 1, HIGH-001); all three
shipped presets, including the secure one, now configure it. Real gaps remain even when
configured: [ADR-0016](../adr/0016-provider-egress-control.md) is drafted but not
yet accepted, no pseudonymization, and this covers only the
owned embedder/generator/reranker/delegated-engine boundary, not PostgreSQL or any other outbound
connection. See
`docs/refactoring/lot-20-data-classification-egress-control.md` for full evidence.

**Escalation only, never silent downgrade:** if a document is re-classified, only escalation
(e.g. `internal` → `confidential`) may happen automatically from new evidence (e.g. a PII pattern
match during redaction, Lot 11c). Downgrading a classification is a deliberate, logged, human
decision — never a side effect of processing.

## 2. Tenant schema

- **`tenant_id`** — the unit of isolation. Every stored `Chunk`/`Document`, every `Query`, and
  every audit event's `AuditEvent.tenant_id` (`contracts/audit.py`, Lot 10) belongs to exactly one
  tenant. Cross-tenant access **is** denied by default, for any manifest that wires a
  `tenant_policy` — this shipped in Lot 11b, confirmed directly against `orchestration/engine.py`
  and `security/policies/tenant_isolation.py`'s `TenantIsolationPolicy`. There is no "shared
  across all tenants" classification level distinct from `public` (a `public`-classified document
  is visible to every tenant precisely because it carries no confidentiality obligation, not
  because tenant scoping is bypassed for it).
- **Resolved since this document was first written**: `core.models.query.Query` now has a
  dedicated `tenant_id: str | None` field — it is no longer buried in `query.metadata`.
  `RAGEngine`'s audit-event construction (`_record_audit_event()`) reads `query.tenant_id or
  "unknown"` directly, not a metadata-dict lookup. `contracts.engine.ExecutionContext.tenant_id`
  (Lot 7) and `Query.tenant_id` (Lot 11b) are both real today, and the API layer populates
  `Query.tenant_id` from the *verified* identity (`TenantContext.tenant_id`) when a
  `token_verifier` is configured — not a caller-supplied, unverified value, for that case. What
  remains genuinely unresolved (see the "important distinction" note in §1 above) is
  classification-*level* propagation specifically — `DataClassification` itself is still not set
  or read anywhere at runtime, unlike `tenant_id`.
- **Identity provider**: Keycloak (OIDC), implemented as `adapters/auth/keycloak_verifier.py`'s
  `KeycloakTokenVerifier` (Lot 11b) — no longer a future design choice.

## 3. PII/secret schema

Canonical category list — `core.enums.PIICategory` — kept in one place so this policy, fixtures,
and `security/redaction/patterns.py` all refer to the same names instead of drifting:

| `PIICategory` | Detected today by | Classification impact |
|---|---|---|
| `EMAIL` | `security/redaction/patterns.py` (`_PATTERNS["email"]`) | Any document/chunk containing one → at least `restricted` |
| `PHONE` | `_PATTERNS["phone_fr_local"]`, `_PATTERNS["phone_fr_intl"]` (FR-only today; other locales are a gap, not in this lot's scope) | `restricted` |
| `IBAN` | `_PATTERNS["iban"]` | `restricted` |
| `API_KEY` | `_PATTERNS["api_key"]` | `restricted` — also a secrets-management concern, not just PII (`.claude/rules/security-layers.md` Layer 05) |
| `SSN` | `_PATTERNS["ssn_us"]` (US format only) | `restricted` |
| `CREDIT_CARD` | `_luhn_valid()` Luhn-checksum scan, no fixed regex label in `_PATTERNS` | `restricted` |

This table is descriptive of *current* detection coverage, not a claim that detection is
exhaustive — `security/redaction/patterns.py`'s docstring already scopes it as V4-track and
FR/US-pattern-only. Expanding pattern coverage is a redaction-module concern
(`.claude/rules/security.md`: "Tout nouveau pattern PII dans `PatternRedactor` doit être couvert
dans `tests/unit/security/test_redaction.py`"), not this policy document's.

## 4. Classification fixtures

`tests/fixtures/data_classification/sample_documents.yaml` provides worked examples — one per
classification level, annotated with the `PIICategory` values (if any) that justify the level, and
a `tenant_id`. These exist so Lot 11b/11c enforcement tests have concrete, agreed-upon inputs to
test against instead of each lot inventing its own. `tests/unit/fixtures/test_data_classification_fixtures.py`
validates the fixture file's shape (every entry has a valid `DataClassification` value and, if
`restricted`, at least one `PIICategory`) — a fixture-validity check, not an enforcement test.

## 5. Open items, updated post-Lot-11b/11c

- Non-FR/US PII locales (e.g. EU-wide formats beyond France) — still open; expand in the
  redaction module when a concrete need arises, per `.claude/rules/security.md`'s
  pattern-addition rule.
- Legal/regulatory mapping (which classification maps to GDPR vs. HIPAA vs. PCI-DSS obligations
  specifically) — still genuinely open. Lot 11c's redaction-before-storage *mechanism* shipped
  without waiting on this mapping being resolved first (redaction is opt-in per manifest today,
  not driven by a classification→regulation lookup), so this is no longer a hard blocker on
  anything already delivered, but the mapping itself remains undone.
- **Classification-level propagation and enforcement — partially closed by Lot 20.**
  `Document.classification`/`Chunk.classification` are now real fields, propagated by every
  registered `Chunker`, and `governance.egress_policy` branches on them (provider-egress, this
  document's §1 "before external calls" requirement). What Lot 20 did **not** build: an
  ingestion-time *classifier* — the value is still explicit, caller-supplied only, exactly the
  "accepting a classification level as an explicit ingestion parameter" option this item
  originally named, not automatic inference from content. `PolicyEngine`/`TenantIsolationPolicy`
  still do not branch on classification (only `tenant_id`) — that remains open, unassigned to any
  lot. See `docs/refactoring/lot-20-data-classification-egress-control.md`.
