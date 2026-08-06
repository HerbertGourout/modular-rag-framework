---
paths:
  - "src/modular_rag/contracts/**/*.py"
---

# Rules — editing contracts

*(Translated to English 2026-08-06 for consistency with the rest of `.claude/rules/` —
see `docs/documentation-audit-2026-08.md`.)*

- Before modifying a Protocol: check every implementation in `adapters/` and the domain
  modules — breaking a Protocol breaks every conformance test.
- After adding a method to a Protocol: update `tests/contract/test_*_conformance.py` to cover
  the new method.
- A new contract file requires an entry in `contracts/__init__.py`.
- Any change affecting layering requires a new ADR under `docs/adr/` (ADRs 0001–0003 are
  reserved).
- Never import from a domain module (`ingestion/`, `retrieval/`, `generation/`…) inside
  `contracts/`.
