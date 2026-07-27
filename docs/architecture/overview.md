# Architecture Overview — Modular RAG Framework

> This document is the technical specification (cahier technique) for the framework.

---

## 1. Objectif

Ce framework fournit un **context OS** pour systèmes RAG et agentiques : un plan de contrôle sur les connaissances, l'orchestration, la mémoire, la gouvernance et le multimodal. Il est construit autour de trois piliers :

1. **Orchestration déclarative** — les pipelines sont décrits en YAML (manifests), pas en Python impératif.
2. **Retrieval composable** — chunking, embedding, indexation, fusion, reranking sont des contrats remplaçables.
3. **Raisonnement agentique vérifiable** — plusieurs agents spécialisés remplacent le seul appel LLM monolithique.

---

## 2. Principes directeurs

| Principe | Implication |
|---|---|
| **Modularité stricte** | Chaque capacité majeure est un contrat (`typing.Protocol`) |
| **Faible couplage** | L'orchestrateur dépend d'interfaces, jamais d'implémentations concrètes |
| **Évaluation native** | Toute brique a un protocole de mesure associé (`contracts/evaluation.py`) |
| **Sécurité par défaut** | Filtrage des entrées et garde-fous en amont du raisonnement |
| **Observabilité native** | Traces, provenance, scores, coûts et latence loggés à chaque étape |
| **Progressivité** | Fonctions avancées (graph, gouvernance, multimodal) optionnelles jusqu'à stabilisation |

---

## 3. Six planes du système

```
┌─────────────────────────────────────────────────────────────┐
│  CONTROL PLANE          manifests, policies, routing        │
├─────────────────────────────────────────────────────────────┤
│  INGESTION PLANE        parsing, chunking, enrichment       │
├────────────────────────┬────────────────────────────────────┤
│  KNOWLEDGE PLANE       │  REASONING PLANE                   │
│  vector/lex/graph      │  planning, agents, generation      │
│  store, reranking      │                                    │
├────────────────────────┴────────────────────────────────────┤
│  SAFETY PLANE           detectors, filters, redaction       │
├─────────────────────────────────────────────────────────────┤
│  EVALUATION PLANE       benchmarks, scorers, dashboards     │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Roadmap V1 → V5

Cette section décrit l'état **cible** de chaque version — ce qu'elle est censée permettre
une fois terminée, indépendamment de ce qui est déjà livré aujourd'hui. Pour l'état réel
(quelles cases sont cochées), voir [ROADMAP.md](../../ROADMAP.md) ; pour la même
progression racontée sans jargon technique, voir [docs/onboarding.md](../onboarding.md),
section 3. Les cinq versions ne sont pas des lots indépendants — chacune s'appuie sur le
pipeline construit par la précédente plutôt que de le remplacer.

### V1 — Core RAG
**Ce que le framework permet :**
- Ingestion de sources (fichiers, dossiers) avec parsing (PDF, Word, HTML, Markdown, texte brut).
- Chunking optimisé (fixe, adaptatif par sections).
- Recherche hybride dense + lexicale (vector + BM25) avec fusion RRF.
- Reranking par cross-encoder.
- Génération sourcée (citations, groundedness) via OpenAI ou Anthropic.
- Sécurité de base : filtrage de requête, détection d'injection, redaction PII.
- Évaluation native : exact match, recall@k, MRR.
- Exposition via API HTTP (FastAPI) et CLI (`mrag ask`, `mrag ingest`).
- Configuration reproductible par manifests YAML versionnés.

### V2 — Agentic + Adaptive
**Ajouts :**
- Routing adaptatif : LLM-only / simple RAG / agentic RAG / graph RAG selon la complexité.
- Runtime multi-agents : coordinator, planner, retriever agent, extractor, synthesizer, validator.
- Workflows multi-étapes (plan → retrieve → synthesize → critique → refine).
- Sécurité multi-étapes : inspection des plans d'agents.
- Traces d'exécution agentique (quel agent, quel outil, quelle durée).

### V3 — Graph Memory
**Ajouts :**
- Extraction de graphe de connaissances depuis le corpus (entités, relations, communautés).
- GraphRAG : interrogation du graphe + sous-graphe contextuel injecté dans le LLM.
- Multi-hop reasoning explicite (A → B → C avec preuves).
- Résumés hiérarchiques par communauté (Louvain).
- Reasoning graphs comme mémoire réutilisable.
- EvoRAG : renforcement / affaiblissement des arêtes par feedback.

### V4 — Governance
**Ajouts :**
- Policy-as-code : règles YAML versionnées dans Git, appliquées à l'exécution.
- Multi-tenant : domaines de contexte séparés (finance, HR, legal…).
- Multi-environment : dev / staging / prod avec politiques progressivement strictes.
- Audit complet : qui a accédé à quoi, quand, avec quel résultat.
- Human-in-the-loop : validation humaine pour les réponses sensibles.
- Risk profiles par pipeline.

### V5 — Multimodal
**Ajouts :**
- Ingestion multimodale : texte, PDF avec images et tableaux, audio, vidéo.
- Index multi-vecteur : texte + image (CLIP/Colpali) + tableaux + segments vidéo.
- MG²-RAG : graphe multi-granularité cross-modal.
- Agents spécialisés par modalité : text_agent, vision_agent, table_agent, video_agent.
- Réponses enrichies : timecodes vidéo, références d'images, extraits de tableaux.

---

## 5. Flux d'exécution V1 (RAG simple)

```
Query
  │
  ▼
SecurityGuard.check_query()          ← safety plane
  │
  ▼
Retriever.retrieve()                 ← knowledge plane
  │
  ▼
Reranker.rerank()                    ← knowledge plane
  │
  ▼
Generator.generate()                 ← reasoning plane
  │
  ▼
SecurityGuard.check_answer()         ← safety plane
  │
  ▼
Telemetry.record_trace()             ← control plane
  │
  ▼
Answer (text + citations + trace_id)
```

---

## 6. Contrats fondateurs

Les contrats de `src/modular_rag/contracts/` sont le cœur immuable du framework. Toute implémentation — interne ou externe — doit satisfaire ces Protocols :

| Contract | Role | V |
|---|---|---|
| `Chunker` | `chunk(doc) → [Chunk]` | V1 |
| `Embedder` | `embed(texts) → [[float]]` | V1 |
| `Indexer` | `index(chunks)` / `delete(ids)` | V1 |
| `Retriever` | `retrieve(query, k) → [RetrievedChunk]` | V1 |
| `Reranker` | `rerank(query, chunks, k) → [RetrievedChunk]` | V1 |
| `Generator` | `generate(query, context, trace) → Answer` | V1 |
| `SecurityGuard` | `check_query(query)` / `check_answer(answer)` | V1 |
| `Evaluator` | `evaluate(query, answer, expected, context)` | V1 |
| `Planner` | `plan(query) → ExecutionPlan` | V2 |
| `Agent` | `run(task) → AgentResult` | V2 |
| `Telemetry` | `record_trace(trace)` | V1 |
| `Storage` | `put/get/delete/exists` | V1 |
| `Redactor` | `redact(text) → str` | V1 |
| `ManifestLoader` | `load(path) → PipelineManifest` | V1 |

---

## 7. Décisions d'architecture

Voir les ADR dans `docs/adr/` :
- [ADR-0001](../adr/0001-modular-architecture.md) — Six planes, séparation contracts/implémentations
- [ADR-0002](../adr/0002-contracts-and-plugins.md) — Protocols + Factory Registry
- [ADR-0003](../adr/0003-security-and-governance.md) — Safety vs Security, policy-as-code

---

## 8. Modèles de données

Les modèles du domaine sont définis dans `src/modular_rag/core/models/`. Ce sont des objets Pydantic v2 — pas d'ORM, pas de base de données. Voir `data-model.md` pour la documentation complète.

| Modèle | Fichier | Frozen | Usage |
|---|---|---|---|
| `Document` | `document.py` | ✓ | Unité d'ingestion : source, contenu brut, métadonnées |
| `Chunk` | `chunk.py` | ✗ | Sous-segment d'un Document, avec embedding optionnel |
| `Query` | `query.py` | ✓ | Requête utilisateur + hint de routing |
| `RetrievedChunk` | `retrieved.py` | ✓ | Chunk + score + rank + méthode de retrieval |
| `Citation` | `answer.py` | ✗ | Pointeur d'une réponse vers un chunk source |
| `Answer` | `answer.py` | ✗ | Texte généré + citations + trace_id |
| `TraceStep` | `trace.py` | ✗ | Latence + tokens d'une étape du pipeline |
| `Trace` | `trace.py` | ✗ | Audit complet d'une exécution (accumulé via `add_step()`) |
| `PolicyRule` | `policy.py` | ✗ | Condition + action (allow/deny/redact/warn) |
| `Policy` | `policy.py` | ✗ | Ensemble de règles scopées à un tenant |
| `Metrics` | `metrics.py` | ✗ | Scores d'évaluation (recall@k, MRR, groundedness…) |

**Invariants clés :**
- `Document` et `Query` sont immutables (`frozen=True`). Toute modification produit une nouvelle instance.
- `Chunk.token_estimate` est une propriété calculée (`len(content.split())`), pas stockée.
- `Trace.add_step()` est la seule façon d'ajouter une étape — elle met à jour atomiquement les totaux `total_latency_ms`, `total_input_tokens`, `total_output_tokens`.
- `Policy.sorted_rules()` retourne les règles triées par priorité décroissante.
- `Metrics.summary()` retourne uniquement les champs non-None.

---

## 9. Wiring manifest → pipeline

Le chemin complet entre un fichier YAML et un pipeline opérationnel :

```
manifests/presets/local-hybrid-rag.yaml
  │
  ▼ app/bootstrap.py → load_manifest(path) → PipelineManifest
  │
  ▼ orchestration/registry.py → ComponentRegistry.default()
  │   # _default_factories maps "fixed" → FixedSizeChunker, "bm25" → BM25Retriever, etc.
  │
  ▼ registry.wire(manifest) → Container
  │   # Reads manifest.chunker.type, manifest.retriever.type …
  │   # Calls factory(config) for each component
  │   # Stores wired instances in Container.components dict
  │
  ▼ app/container.py → Container (holds all wired instances)
  │
  ▼ orchestration/engine.py → RAGEngine(container)
  │   # engine.ingest() / engine.answer() use container.get(Chunker), etc.
  │
  ▼ cli/main.py or api/routes.py → calls engine methods
```

Pour câbler un nouveau composant :
1. Implémenter le contrat correspondant dans `contracts/`.
2. Ajouter la factory dans `orchestration/registry.py → _default_factories`.
3. Référencer le type dans le manifest YAML : `chunker: {type: my_chunker, ...}`.

---

## 10. Pipeline d'ingestion (V1 détail)

```
Fichier (PDF / Markdown / texte brut)
  │
  ▼ ingestion/parsers/
  │   TextParser → Document  (pour .txt, .md, .html)
  │   PDFParser  → Document  (pour .pdf, via PyMuPDF)
  │
  ▼ ingestion/normalizers/TextNormalizer.normalize(doc)
  │   • Collapse excessive newlines (3+ → 2)
  │   • Collapse excessive spaces (2+ → 1)
  │   • Strip leading/trailing whitespace
  │   → nouveau Document (frozen → nouvelle instance)
  │
  ▼ ingestion/enrichers/MetadataEnricher.enrich(doc)
  │   • Calcule word_count, lang, reading_level
  │   • Fusionne avec metadata existante
  │   → nouveau Document
  │
  ▼ contracts/chunking.Chunker.chunk(doc) → list[Chunk]
  │   FixedSizeChunker  : fenêtres de N tokens avec overlap
  │   AdaptiveChunker   : coupe sur les titres Markdown (##, ###)
  │
  ▼ Embedder.embed([c.content for c in chunks]) → list[list[float]]
  │   → écrit embedding dans chaque Chunk en place
  │
  ▼ Indexer.index(chunks) → int
      QdrantStore : upsert en tant que PointStruct (vector + payload)
      BM25Retriever : reconstruit l'index BM25 sur le corpus
```

Note : L'embedding et l'indexation se font dans `RAGEngine.ingest()`, pas dans `ingest_path()`. La séparation est intentionnelle — `ingest_path()` est testable sans service externe.

---

## 11. Algorithme de retrieval hybride (RRF)

Le retrieval hybride combine deux listes de résultats classées (vecteur dense + BM25 lexical) en une liste fusionnée via **Reciprocal Rank Fusion** :

```
RRF_score(d) = Σᵢ  1 / (rrf_k + rankᵢ(d))

  où :
    rrf_k  = 60  (constante de lissage, standard de la littérature)
    rankᵢ  = rang du document d dans la liste i (1-based)
    Σ      = somme sur toutes les listes de résultats (vector, BM25)
```

Exemple avec 2 listes :
```
document "Q4 revenue"
  rank_vector = 3  → 1 / (60 + 3) = 0.0159
  rank_bm25   = 1  → 1 / (60 + 1) = 0.0164
  RRF_score   = 0.0159 + 0.0164 = 0.0323
```

Le ratio vecteur/BM25 dans le preset `local-hybrid-rag.yaml` est **0.7 / 0.3** : les résultats vectoriels ont plus de poids car ils capturent la sémantique, tandis que BM25 booste les correspondances exactes de termes techniques.

Après fusion, les chunks sont re-classés par `RRF_score` décroissant. Un reranker cross-encoder affine ensuite ce classement sur les top-k (défaut : 5).

---

## 12. Hiérarchie des erreurs

Toutes les exceptions du framework héritent de `ModularRAGError` (défini dans `core/errors.py`). L'arborescence complète :

```
ModularRAGError                     ← base de toutes les erreurs du framework
├── ConfigurationError              ← manifest ou settings invalide
│   └── ManifestError               ← YAML non chargeable ou non validable
├── RegistryError                   ← composant introuvable dans le registre
├── IngestionError                  ← parsing ou chunking échoué
├── IndexingError                   ← écriture dans le vector/lexical store échouée
├── RetrievalError                  ← opération de retrieval échouée
├── GenerationError                 ← appel LLM échoué ou réponse inutilisable
├── SecurityError                   ← guard bloque une requête ou une réponse
│   └── PolicyViolationError        ← action pipeline viole une policy déclarée
├── EvaluationError                 ← scoring ou benchmark échoué
├── GraphError                      ← construction ou traversée du graphe échouée (V3)
├── AgentError                      ← tâche agent échouée (V2)
└── StorageError                    ← opération backend de stockage échouée
```

**Règle de gestion :** attraper l'exception la plus spécifique possible. N'attraper `ModularRAGError` qu'au niveau des handlers HTTP/CLI pour renvoyer une réponse d'erreur générique. Ne jamais avaler silencieusement une `SecurityError` — elle doit toujours être loggée.
