# CLAUDE.md — Security module

Read this file before editing `src/modular_rag/security/`. This module handles untrusted content,
tenant boundaries, policy decisions, redaction, audit, feedback, and human review. Treat logs,
traces, feedback corrections, and provider payloads as possible sensitive-data paths.

## Architectural boundary

Security is a domain module. It may import `contracts/`, `core/`, and its own package; it must not
import sibling domains such as `retrieval/`, `generation/`, `ingestion/`, `agents/`, `memory/`, or
`eval/`. Concrete composition belongs in `app/default_factories.py` and selection belongs in YAML
manifests.

The currently implemented controls are useful safeguards, not a compliance certification.
Classification-aware, deny-by-default provider egress shipped in Lot 20
(`governance.egress_policy`, ADR-0016) and is mandatory the moment a manifest wires a known
remote provider type (`openai`/`anthropic`/`openai-embeddings`). Deployments sending content to
any other external LLM or embedding API still need an external gateway/control or must restrict
themselves to approved local providers.

ADR-0015 accepts a broader portable assurance direction. It is not authority to add or change a
Protocol until the separate contract-change work is approved.

## Current contracts and implementations

### Content guard

`contracts/security.py` defines the runtime-checkable `SecurityGuard` Protocol:

```python
def check_query(self, query: Query) -> GuardResult: ...
def check_answer(self, answer: Answer) -> GuardResult: ...
def name(self) -> str: ...
```

`GuardResult` contains `allowed`, optional `reason`, optional `modified_content`, and
`risk_score`. The reference implementation is `filters/basic_guard.py`. It is a first-line,
pattern-based defense, not proof that arbitrary prompt injection or corpus poisoning is detected.

### Redaction

`PatternRedactor` in `redaction/patterns.py` implements `Redactor.redact(text)`. Extend the existing
pattern set and tests rather than duplicating regex families. Redaction is destructive masking; it
does not provide reversible pseudonymization or establish whether an external transfer is lawful.

### Policy and tenant isolation

- `PolicyEngine.enforce_query(query)` evaluates enabled `Policy` rules and fails closed on
  evaluation errors.
- `TenantIsolationPolicy` implements the `TenantPolicy` contract:
  `enforce_query`, `enforce_ingest`, and `filter_chunks`.
- There is no shipped generic `RBACPolicy` class. API roles and policy rules must be documented
  according to their actual enforcement points.

### Audit, feedback, and review

- Audit sinks record governed events; never include raw secrets or unnecessary content.
- Feedback sinks persist the `contracts/feedback.py` model. Free-text correction content is
  rejected unless a redactor is configured, then redacted before storage.
- `HumanReviewGate` and the PostgreSQL review adapter implement the `ReviewQueue` contract.
  Resolution is terminal; a resolved item must not be overwritten.
- In-memory implementations are functional references, not durable production storage.

## Mandatory implementation rules

1. Never log full query, answer, document, correction, credential, or provider payload text.
   Prefer identifiers, lengths, counts, and bounded classifications.
2. Load credentials from the provider's supported environment/configuration mechanism and never
   echo their values. The repository currently uses standard provider variables such as
   `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`; do not invent an undocumented secret convention.
3. Keep configurable thresholds in constructor/manifest configuration. Preserve the existing
   `BasicSecurityGuard` risk scale unless an accepted design explicitly changes its semantics.
4. Fail closed when a declared mandatory policy, tenant, audit, redaction, or future egress control
   cannot execute. Do not silently downgrade a requested control.
5. Keep safety checks, access/policy enforcement, audit, and redaction as distinct components even
   when the orchestration flow composes them.
6. Register a new built-in through `app/default_factories.py`; add or update its manifest schema
   only when necessary.
7. Use lazy imports for optional heavy dependencies.

## Minimal guard example

```python
from modular_rag.contracts.security import GuardResult
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query


class ExampleGuard:
    def name(self) -> str:
        return "example"

    def check_query(self, query: Query) -> GuardResult:
        return GuardResult(allowed=True, risk_score=0.0)

    def check_answer(self, answer: Answer) -> GuardResult:
        return GuardResult(allowed=True, risk_score=0.0)
```

Use `result.allowed`; `evaluate()` and `result.is_safe` are not part of the current contract.

## Required tests

- Unit tests for allowed, denied, malformed, boundary, and false-positive cases.
- Contract conformance for every new Protocol implementation.
- Manifest/factory tests for a new built-in component.
- Tenant isolation tests for both query and ingestion paths when tenancy changes.
- Parity tests for every governance control that must work under both native and delegated engines.
- Redaction tests that assert sensitive values are absent from persisted/logged output.

Run the narrow affected tests, then the repository checks. Do not run provider-backed integration
or end-to-end tests without confirmed services and credentials.

## Before finalizing

- [ ] No sibling-domain import or concrete wiring outside the composition root.
- [ ] No raw sensitive content or secrets in logs, traces, reports, or exceptions.
- [ ] Declared controls fail closed and have negative-path tests.
- [ ] Contract, factory, manifest, and documentation changes agree.
- [ ] Claims distinguish implemented safeguards (including Lot 20 provider egress), deployment
      responsibility, and the unbuilt Lot 22 existing-application adapter.
- [ ] A Protocol change has an accepted ADR and migration/conformance coverage.

## References

- `contracts/security.py`, `contracts/feedback.py`, `contracts/review.py`
- `docs/architecture/security.md`
- `docs/architecture/data-classification-policy.md`
- `docs/architecture/threat-model.md`
- `docs/adr/0003-security-and-governance.md`
- `docs/refactoring/lot-20-data-protection-and-provider-egress.md`
