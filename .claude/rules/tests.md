---
paths:
  - "tests/**/*.py"
---

# Rules — writing tests

*(Translated to English 2026-08-06 for consistency with the rest of `.claude/rules/` —
see `docs/documentation-audit-2026-08.md`.)*

- `tests/unit/`: no external services. Don't mock what can be tested directly.
- `tests/contract/`: use `isinstance(obj, Protocol)` to check conformance. Parametrize over
  every implementation of the Protocol.
- `tests/integration/`: requires Qdrant on localhost:6333. Mark with `@pytest.mark.integration`.
- `tests/e2e/`: full pipeline with a real LLM. Mark with `@pytest.mark.e2e`.
- `VectorRetriever` and `HybridRetriever` are excluded from contract tests (they need Qdrant).
- Test files mirror `src/`: `tests/unit/ingestion/chunkers/test_fixed.py` for
  `src/modular_rag/ingestion/chunkers/fixed.py`.
- Every new Protocol implementation needs an entry in the matching conformance test.
