---
name: validate-security
description: Validate security-sensitive changes against current layering, data-flow, governance, and test requirements
---

# Validate Security

Use this checklist for changes that affect guards, policies, tenancy, audit, feedback, review,
credentials, redaction, provider adapters, or external data transfer. It supplements the repository
checks; it is not a compliance assessment or certification.

## 1. Establish the sensitive data flow

List each source, transformation, storage target, log/trace/report, and external destination touched
by the diff. Confirm that free text, document content, answers, and corrections are treated as
potentially sensitive. Record any control that remains deployment-owned.

Classification-aware, deny-by-default provider egress shipped in Lot 20
(`governance.egress_policy`, ADR-0016) and is mandatory the moment a manifest wires a known
remote provider type (`openai`/`anthropic`/`openai-embeddings`). Verify it is configured with a
real (not `max_classification: restricted`-only) ceiling before treating an external-provider path
as protected, and require an approved external gateway/policy or a local provider for any provider
type this control does not yet cover.

## 2. Run deterministic repository checks

```powershell
.\.venv\Scripts\python.exe scripts\check_layering.py --strict
.\.venv\Scripts\python.exe -m ruff check . --select E,F,I,N,W,UP,B,C4
.\.venv\Scripts\python.exe scripts\check_docs.py
```

The layering checker, rather than an ad hoc grep loop, is the source of truth for project-layer
imports. Domain modules may import only `core`, `contracts`, and themselves; concrete composition
belongs in `app/default_factories.py`.

## 3. Inspect secrets and logging

Use `rg` to inspect the changed surface and review every match, including false positives:

```powershell
rg -n -i "api[_-]?key|secret|password|token|query\.text|answer\.text|correction_text" src tests manifests
```

Reject hard-coded credentials and logs/traces/errors that expose raw sensitive text. Environment
variable names and test placeholders are not secrets, but must still be handled deliberately.
Never print a credential value in validation output.

## 4. Verify declared controls are real and fail closed

- Guards use `check_query`/`check_answer` and `GuardResult.allowed`.
- Tenant policy covers query, ingestion, and retrieved-chunk filtering where applicable.
- Policy evaluation errors deny rather than silently pass.
- Free-text feedback correction is not stored without configured redaction.
- Audit/review persistence errors follow the declared availability policy.
- A manifest cannot select an unsupported engine/control combination; LangGraph-native-only
  controls are rejected rather than ignored.
- Optional provider dependencies remain lazily imported.

Do not describe API authentication roles as a generic RBAC system unless the code actually
implements the claimed resource/permission semantics.

## 5. Run affected tests

Run unit and contract tests for the precise change, plus manifest/bootstrap tests for wiring. Add
negative cases for denial, missing identity, malformed policy, redaction absence, idempotency, and
unsupported-engine selection as relevant. Do not run provider-backed integration tests without
confirmed services and credentials.

## Report format

For each section report `PASS`, `FAIL`, or `NOT APPLICABLE`, with `file:line` evidence for failures.
Separate:

- controls implemented by the framework;
- controls required from deployment infrastructure;
- accepted limitations and planned work.

Do not mark validation passed while a declared mandatory control can be silently bypassed.
