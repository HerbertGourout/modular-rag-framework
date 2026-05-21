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
