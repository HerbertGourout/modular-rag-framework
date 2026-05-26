---
paths:
  - "tests/**/*.py"
---

# Règles — écriture des tests

- `tests/unit/` : aucun service externe. Ne pas mocker ce qui peut être testé directement.
- `tests/contract/` : utiliser `isinstance(obj, Protocol)` pour vérifier la conformité. Parametrize sur toutes les implémentations du Protocol.
- `tests/integration/` : nécessite Qdrant sur localhost:6333. Marquer avec `@pytest.mark.integration`.
- `tests/e2e/` : pipeline complet avec vrai LLM. Marquer avec `@pytest.mark.e2e`.
- `VectorRetriever` et `HybridRetriever` sont exclus des tests contract (nécessitent Qdrant).
- Les fichiers de tests mirent `src/` : `tests/unit/ingestion/chunkers/test_fixed.py` pour `src/modular_rag/ingestion/chunkers/fixed.py`.
- Chaque nouvelle implémentation de Protocol nécessite une entrée dans le test de conformité correspondant.
