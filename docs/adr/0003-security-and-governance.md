# ADR-0003 — Security-by-Default and Policy-as-Code (V1 → V4)

**Status:** Accepted  
**Date:** 2026-05-20  
**Authors:** Herbert Gourout, Publicis Data Specialists

> **Amendment, 2026-08 (the decision itself — Safety≠Security, guard chain, policy-as-code — is
> unchanged and still accepted; several things this ADR scoped as future work have since shipped
> or moved, corrected here rather than left to mislead a reader):**
> - **Policy-as-Code is native and live today, not "V4."** `PolicyEngine` is wired into
>   `RAGEngine._run_steps()` and runs on every governed query, per Lot 11b — see
>   [CLAUDE.md block 09](../../CLAUDE.md#09--roadmap-v1--v5-with-strategic-features), which
>   places Policy Engine at V2.0, P0 priority, not V4. The YAML-file-per-policy layout shown in
>   this ADR's example (`policies/no-pii-export.yaml`) was never the shipped mechanism — policies
>   are declared inline under a manifest's `governance.policy_engine.config.policies`, validated
>   by the same Pydantic schema as the rest of the manifest. See
>   [security.md](../architecture/security.md) for the real, current mechanism.
> - **`AdversarialDetector` is real but not "added to the guard chain."** The class exists
>   (`security/detectors/adversarial.py`) but is not registered in `app/default_factories.py`
>   under any type name, so no manifest can select it — see security.md's "Components that exist
>   but aren't wired" section.
> - **"Agent plan inspection: coordinator checks..." describes a native multi-agent coordinator
>   that no longer exists.** Per [ADR-0005](0005-document-ai-control-plane-boundary.md) §5.2
>   (accepted 2026-08-04), generic multi-agent orchestration is delegated to a selected external
>   engine; the coordinator prototype this line refers to was removed in
>   [Lot 17](../refactoring/lot-17-prototype-retirement.md). There is no native agent-plan
>   inspection step today.
> - **The "Open item (V4)" about adding tenant context to `Query`** is resolved: `Query.tenant_id`
>   is a real field (Lot 11b), enforced fail-closed by `TenantIsolationPolicy` — see
>   [threat-model.md](../architecture/threat-model.md).
> - The Safety-vs-Security separation itself, and `security/detectors/` +
>   `security/filters/` vs. `security/policies/` as the dividing line, remain exactly as decided
>   below and are unaffected by the above.

---

## Context

RAG systems face specific attack surfaces (Secure RAG surveys):
- **Prompt injection** via user queries or poisoned context.
- **Data poisoning** (malicious documents in the corpus).
- **Data exfiltration** (agent actions leaking PII or secrets).
- **Context flooding** (DoS via very long queries).

Governance at scale (V4) also requires:
- Tenant isolation (different knowledge bases per business unit).
- Environment-aware policies (dev is lax, prod is strict).
- Auditable traces of every retrieval and generation decision.

---

## Decision

### Layer 1 — Safety (V1)
`SecurityGuard` protocol applied at two points in the pipeline:
- **Pre-retrieval**: `check_query()` — blocks injections, oversized queries, blocked terms.
- **Post-generation**: `check_answer()` — applies redaction, checks for PII leakage.

Built-in: `BasicSecurityGuard` (injection patterns, length check) and `PatternRedactor` (email, IBAN, API keys).

### Layer 2 — Adversarial Defence (V2)
`AdversarialDetector` added to the guard chain. Detects exfiltration patterns (webhook calls, mass data export). Agent plan inspection: coordinator checks that no planned tool call violates a policy before executing.

### Layer 3 — Policy-as-Code (V4)
Policies are YAML files loaded at pipeline startup and enforced by `PolicyEngine`. Rules use a condition language (initially simple keyword matching, extensible to CEL or Rego):

```yaml
# policies/no-pii-export.yaml
name: no-pii-export
rules:
  - name: block-mass-export
    condition: "output all documents"
    action: deny
    priority: 100
```

### Separation: Safety vs. Security
- **Safety** (`security/detectors/`, `security/filters/`): input/output correctness, adversarial inputs.
- **Security** (`security/policies/`): access control, tenant isolation, compliance.
These are kept in separate sub-packages to allow independent evolution.

---

## Consequences

**Positive**
- Every pipeline has at least one guard layer available (even if disabled by default in dev).
- Policy changes require only a YAML diff, not a code deployment.
- The `Trace` model records whether each guard was triggered, enabling audit.

**Negative**
- Keyword-based policy conditions are limited; full CEL/OPA integration is a V4 work item.
- Multiple guard layers add latency; each layer should target < 5 ms.

**Open item (V4)**
- Integrate OPA (Open Policy Agent) as the policy evaluation engine for complex rules.
- Add multi-tenant context to `Query` so policies can scope by tenant without parsing the question text.
