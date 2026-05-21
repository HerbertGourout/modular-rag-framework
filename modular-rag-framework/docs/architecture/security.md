# Security Architecture

## Attack surfaces (Secure RAG taxonomy)

| Surface | Example | Defence |
|---|---|---|
| Prompt injection (query) | "Ignore previous instructions…" | `BasicSecurityGuard.check_query()` |
| Prompt injection (context) | Poisoned document in corpus | Anti-poisoning enricher (V2) |
| Data exfiltration | Agent calls webhook with PII | `AdversarialDetector` + policy DENY |
| Context flooding | 10 000-token query | `max_query_length` guard |
| PII leakage in answer | LLM echoes email from chunk | `PatternRedactor` on answer |
| Data poisoning | Malicious chunks skew retrieval | Provenance tracking + source allowlist |

## Guard chain (V1)

```
Query → BasicSecurityGuard.check_query()
  ↓ allowed
Retrieval → [chunks]
  ↓
Generation → Answer
  ↓
BasicSecurityGuard.check_answer()
  ↓
PatternRedactor.redact(answer.text)   [if enabled]
  ↓
Final Answer
```

## Policy lifecycle (V4)

```
Git commit (policies/*.yaml)
  → CI validation (policy linter)
  → Pipeline loads PolicyEngine(policies)
  → Every query/agent action evaluated against rules
  → Violations logged to audit trail + SIEM
```

## Risk levels

| Level | Controls required |
|---|---|
| Low (dev, internal tools) | BasicSecurityGuard disabled OK |
| Medium (internal, sensitive data) | BasicSecurityGuard + PatternRedactor |
| High (public-facing, regulated) | + AdversarialDetector + PolicyEngine + human review for high-risk answers |
