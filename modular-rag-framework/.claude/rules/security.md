---
paths:
  - "src/modular_rag/security/**/*.py"
---

# Règles — module security

- **Safety** (injection de prompt, PII, toxicité) → `security/filters/` ou `security/redaction/`
- **Security** (RBAC, isolation tenant, application de policies) → `security/policies/`
- Ne jamais mélanger les deux dans un même fichier.
- Ne jamais importer depuis les modules domaine (`ingestion/`, `retrieval/`, `generation/`) dans `security/`.
- Tout nouveau guard ou detector doit implémenter le Protocol `SecurityGuard` de `contracts/security.py`.
- Tout nouveau pattern PII dans `PatternRedactor` doit être couvert dans `tests/unit/security/test_redaction.py`.
- `risk_score` : 0.9 = injection, 0.8 = terme bloqué, 0.5 = longueur dépassée, 0.0 = OK.
