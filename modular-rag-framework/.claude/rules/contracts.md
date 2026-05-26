---
paths:
  - "src/modular_rag/contracts/**/*.py"
---

# Règles — édition des contrats

- Avant de modifier un Protocol : vérifier toutes les implémentations dans `adapters/` et les modules domaine — casser un Protocol casse tous les tests de conformité.
- Après avoir ajouté une méthode à un Protocol : mettre à jour `tests/contract/test_*_conformance.py` pour couvrir la nouvelle méthode.
- Un nouveau fichier de contrat requiert une entrée dans `contracts/__init__.py`.
- Tout changement qui affecte le layering nécessite un nouvel ADR sous `docs/adr/` (ADRs 0001–0003 sont réservés).
- Ne jamais importer depuis un module domaine (`ingestion/`, `retrieval/`, `generation/`…) dans `contracts/`.
