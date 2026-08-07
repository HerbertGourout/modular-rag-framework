---
paths:
  - "src/modular_rag/security/**/*.py"
---

# Rules — security module

*(Translated to English 2026-08-06 for consistency with the rest of `.claude/rules/` —
see `docs/archive/documentation-audit-2026-08.md`.)*

- **Safety** (prompt injection, PII, toxicity) → `security/filters/` or `security/redaction/`
- **Security** (RBAC, tenant isolation, policy enforcement) → `security/policies/`
- Never mix the two in the same file.
- Never import from domain modules (`ingestion/`, `retrieval/`, `generation/`) inside `security/`.
- Any new guard or detector must implement the `SecurityGuard` Protocol from
  `contracts/security.py`.
- Any new PII pattern in `PatternRedactor` must be covered in
  `tests/unit/security/test_redaction.py`.
- `risk_score`: 0.9 = injection, 0.8 = blocked term, 0.5 = length exceeded, 0.0 = OK.
