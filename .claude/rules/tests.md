---
paths:
  - "tests/**/*.py"
---

# Rules — writing tests

*(Translated to English 2026-08-06 for consistency with the rest of `.claude/rules/` —
see `docs/archive/documentation-audit-2026-08.md`.)*

- `tests/unit/`: no external services. Don't mock what can be tested directly.
- `tests/contract/`: use `isinstance(obj, Protocol)` to check conformance. Parametrize over
  every implementation of the Protocol.
- `tests/integration/`: requires Qdrant on localhost:6333. Mark with `@pytest.mark.integration`.
- `tests/e2e/`: full pipeline against real backing services (Qdrant, plus PostgreSQL for a
  governed/audited preset). Mark with `@pytest.mark.e2e`. An LLM API key is only required when
  the scenario's manifest wires an LLM-backed generator — a deterministic preset (e.g.
  `adapters.embeddings.deterministic_embedder`/`generation.synthesizers.deterministic_gen`) needs
  none.
- `VectorRetriever` and `HybridRetriever` are excluded from contract tests (they need Qdrant).
- Test files mirror `src/`: `tests/unit/ingestion/chunkers/test_fixed.py` for
  `src/modular_rag/ingestion/chunkers/fixed.py`.
- Every new Protocol implementation needs an entry in the matching conformance test.
