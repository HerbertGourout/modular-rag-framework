# ADR-0003 — Security-by-Default and Policy-as-Code (V1 → V4)

**Status:** Accepted  
**Date:** 2026-05-20  
**Authors:** Herbert Gourout, Publicis Data Specialists

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
