# Lot 11a — Threat Model and Data Classification Policy

**Status:** COMPLETE
**Date:** 2026-08-05
**Depends on:** none directly; consumes Lot 7's `ExecutionContext.tenant_id` and Lot 10's
`AuditEvent`/`Trace` as reference points for what's already in place.
**Blocks:** Lot 11b (identity/tenant propagation needs the classification scheme to enforce
against — this is the plan's own stated dependency).

## What was done

Per `docs/refactoring-plan.md`'s explicit scoping — "Paper-and-fixture deliverable; no
enforcement code yet" — this lot produced documentation, vocabulary types, and test fixtures.
**No `PolicyEngine`, `SecurityGuard`, `RAGEngine`, `Container`, or manifest-schema code was
changed.**

- **`docs/architecture/threat-model.md`** (new): assets table, a trust-boundary Mermaid diagram
  (the "no authentication today" boundary is called out explicitly as the framework's most
  significant open one), a threat-actor table, and a STRIDE analysis. Every threat row cites the
  concrete mechanism in this codebase (e.g. `api/__init__.py`'s
  `raise HTTPException(status_code=500, detail=str(exc))` leaking raw exception text — an
  Information Disclosure threat owned by Lot 16a) rather than a generic textbook description, and
  is cross-referenced to the lot that owns closing it (11b, 11c, 16a, 16c) or flagged as not yet
  assigned (document provenance/anti-poisoning, policy tamper-detection).
- **`docs/architecture/data-classification-policy.md`** (new): four classification levels
  (`public`/`internal`/`confidential`/`restricted`) with definitions, framework-specific examples,
  and target handling requirements per level; a tenant schema section that names the exact
  existing gap (`Query` has no `tenant_id` field yet, `RAGEngine._audit()`'s
  `query.metadata.get("tenant_id", "unknown")` placeholder from Lot 10, and
  `ExecutionContext.tenant_id`'s existing-but-unenforced field from Lot 7); and a PII/secret
  schema mapping `core.enums.PIICategory` to what `security/redaction/patterns.py` already
  detects. Default classification when unclassified is `restricted` (fail-closed), matching the
  plan's own deny-by-default invariant for Lot 11b.
- **`core/enums.py`**: two new `StrEnum`s, `DataClassification` (4 levels) and `PIICategory` (6
  categories mirroring `security/redaction/patterns.py`'s existing detection labels). Pure
  vocabulary — nothing reads or enforces these yet; both docstrings say so explicitly to prevent
  overclaiming. Tests: `tests/unit/core/test_models.py::test_data_classification_values`,
  `::test_pii_category_values`.
- **`tests/fixtures/data_classification/sample_documents.yaml`** (new): six worked examples, one
  per classification level (plus two `restricted` variants), each with a `tenant_id`,
  `pii_categories`, and a written `rationale`. Includes a second `tenant_id`
  (`other-tenant`) specifically so Lot 11b's cross-tenant-denial tests have a fixture to use
  without inventing their own.
- **`tests/unit/fixtures/test_data_classification_fixtures.py`** (new, 7 tests): validates the
  fixture's own shape — every classification value is a real `DataClassification`, every PII
  category is a real `PIICategory`, every `restricted` entry declares at least one PII category,
  all four levels are represented, every entry has a `tenant_id` and non-empty rationale, and at
  least two distinct tenants exist. This is fixture-validity checking, matching the
  "characterization, not enforcement" pattern already used in Lot 4 — not a test of any
  enforcement behavior, because none exists yet.
- Linked the two new docs from `docs/architecture/_index.md`'s navigation table and from
  `docs/architecture/security.md`'s header.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 324 tests total (261 unit + 63 contract, up from 315 at Lot 10): +7 fixture-validity tests,
  +2 enum-value tests.
- mypy baseline unchanged at 35.

## Lot 11a acceptance (per `docs/refactoring-plan.md` §6)

"Written threat model and data-classification policy, reviewed by the team" — the "reviewed by
the team" clause is currently satisfied by sole decision authority (Herbert Gourout, per
`docs/refactoring/lot-0-baseline.md` §2 — no additional team members are onboarded yet, so there
is no separate reviewer to route this through).

## Next

Lot 11b (identity/tenant propagation): give `Query`/`ExecutionContext` a real, enforced tenant
identity (target: Keycloak OIDC, per the plan's decision log), replace
`RAGEngine._audit()`'s `query.metadata.get("tenant_id", "unknown")` placeholder with the enforced
value, and implement fail-closed policy enforcement before indexing/retrieval/generation —
against the classification scheme and fixtures this lot produced.
