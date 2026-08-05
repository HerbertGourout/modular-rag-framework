# Data Classification Policy

**Status:** Lot 11a deliverable (`docs/refactoring-plan.md` Phase C) — a paper-and-fixture
policy, not enforcement code. Nothing in the codebase reads or acts on the classification level
of a document, chunk, or query yet. `core.enums.DataClassification` exists as shared vocabulary
for this policy and for the fixtures below; wiring it into retrieval/generation/policy
enforcement (deny-by-default on policy-engine error, tenant-scoped filtering) is
[Lot 11b](../refactoring-plan.md) scope.

This document exists because [Lot 11b](../refactoring-plan.md) ("Propagate authenticated identity
and tenant through `ExecutionContext`; enforce fail-closed policy before indexing, retrieval, and
generation") needs a classification scheme to enforce *against* before it can be built —
`docs/refactoring-plan.md` names this as a blocking dependency ("Blocks 11b, since identity/tenant
propagation needs the classification to enforce against").

---

## 1. Classification levels

Four levels, each strictly more restrictive than the last. A document, chunk, or answer carries
exactly one level at a time — the *highest* level of any information it contains (a chunk mixing
public and confidential content is classified `confidential`, not split).

| Level | Definition | Example in this framework's own domain | Handling requirement (target, Lot 11b/11c) |
|---|---|---|---|
| `public` | Safe for unauthenticated or any-tenant access; no confidentiality obligation | Published documentation, marketing material, open-source code comments | No guard required; may be cached/logged verbatim |
| `internal` | Safe within the organization/tenant, not for external release | Internal runbooks, non-customer-identifying internal metrics, this repository's own source code | Tenant-scoped retrieval; `BasicSecurityGuard` recommended |
| `confidential` | Business-sensitive or third-party data under a confidentiality obligation | Client contracts, unreleased campaign strategy, vendor pricing | Tenant-scoped retrieval mandatory; `PatternRedactor` on answers; audit evidence required (Lot 10) |
| `restricted` | Regulated personal data or data whose exposure creates legal/compliance exposure | Any document containing an item from the PII/secret schema below (§2), health data, payment data | All of `confidential`, plus mandatory redaction before storage/logging/external calls (Lot 11c), human review for low-confidence answers, narrowest-need-to-know tenant scoping |

**Default when unclassified:** `restricted`. An ingestion pipeline that has not explicitly
classified a document must not assume a lower level than `restricted` once enforcement lands
(Lot 11b) — this is a fail-closed default, matching the plan's own invariant for policy-engine
errors ("deny-by-default... never allow by default").

**Escalation only, never silent downgrade:** if a document is re-classified, only escalation
(e.g. `internal` → `confidential`) may happen automatically from new evidence (e.g. a PII pattern
match during redaction, Lot 11c). Downgrading a classification is a deliberate, logged, human
decision — never a side effect of processing.

## 2. Tenant schema

- **`tenant_id`** — the unit of isolation. Every stored `Chunk`/`Document`, every `Query`, and
  every audit event's `AuditEvent.tenant_id` (`contracts/audit.py`, Lot 10) belongs to exactly one
  tenant. Cross-tenant access is denied by default once Lot 11b lands; there is no "shared across
  all tenants" classification level distinct from `public` (a `public`-classified document is
  visible to every tenant precisely because it carries no confidentiality obligation, not because
  tenant scoping is bypassed for it).
- **Today's gap** (recorded in `docs/refactoring-plan.md` §2, "Tenant isolation... Tenant is
  descriptive metadata, not an enforced storage filter"): `core.models.query.Query` has no
  dedicated `tenant_id` field. `RAGEngine._audit()` (Lot 10) reads `query.metadata.get("tenant_id",
  "unknown")` as a placeholder. `contracts.engine.ExecutionContext.tenant_id` already exists as a
  required field (Lot 7) — Lot 11b's job is making callers actually populate and enforce it,
  including on `Query` itself or a wrapping context, not this lot's.
- **Identity provider**: Keycloak (OIDC), per the infra-stack decision already recorded in
  `docs/refactoring-plan.md`'s decision log (2026-08-03). Claims mapping (which OIDC claim becomes
  `tenant_id` vs. `user_id`) is Lot 11b's design, not fixed here.

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

## 5. Open items (not resolved by this lot)

- Non-FR/US PII locales (e.g. EU-wide formats beyond France) — expand in the redaction module
  when a concrete need arises, per `.claude/rules/security.md`'s pattern-addition rule.
- Legal/regulatory mapping (which classification maps to GDPR vs. HIPAA vs. PCI-DSS obligations
  specifically) — flagged in `docs/refactoring-plan.md` §10 as a still-open dependency before
  Lot 11c's redaction-before-storage work.
- Automatic classification (an ingestion-time classifier that assigns a level from content) is out
  of scope entirely for V1; today classification is either fixture-defined (for tests) or, once
  Lot 11b lands, provided by whoever calls the ingestion API.
