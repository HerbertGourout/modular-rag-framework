# Structure complète du Modular RAG Framework — Explication exhaustive

> Ce document décrit chaque dossier, chaque fichier et chaque concept du framework dans les moindres détails, avec le rôle actuel et le rôle futur (V1→V5) de chacun.

---

## Vue d'ensemble de l'arborescence racine

```
modular-rag-framework/
├── src/                          ← Code source principal
│   └── modular_rag/              ← Package Python installable
├── tests/                        ← Suite de tests (unit, contract, integration, e2e)
├── docs/                         ← Documentation technique complète
├── manifests/                    ← Configurations YAML de pipelines
├── examples/                     ← Applications exemples exécutables
├── benchmarks/                   ← Benchmarks de performance (futur)
├── scripts/                      ← Scripts utilitaires et audits locaux
├── .claude/                      ← Skills, hooks et settings Claude Code
├── .codex/                       ← Notes projet Codex
├── AGENTS.md                     ← Instructions Codex et stratégie reviewer
├── .gitlab/                      ← Templates CI/CD GitLab
├── pyproject.toml                ← Configuration du projet Python
├── README.md                     ← Pitch, vision, API cible
├── CLAUDE.md                     ← Instructions pour Claude Code
├── CLAUDE.local.example.md       ← Template de preferences Claude Code locales
├── ROADMAP.md                    ← Jalons V1→V5 avec checkboxes
├── CHANGELOG.md                  ← Historique des versions
├── CONTRIBUTING.md               ← Guide de contribution
└── LICENSE                       ← Apache License 2.0
```

---

## FICHIERS RACINE

### `pyproject.toml`
Configuration centrale du projet. Remplace `setup.py` + `setup.cfg`.

**Build system** : Hatchling. Le package se trouve dans `src/modular_rag/`.

**Dépendances runtime (noyau minimal, toujours installées)**

| Paquet | Version | Rôle |
|---|---|---|
| `pydantic` | ≥2.7 | Modèles de données, validation |
| `pydantic-settings` | ≥2.3 | Lecture des variables d'environnement |
| `pyyaml` | ≥6.0 | Chargement des manifests YAML |
| `httpx` | ≥0.27 | Client HTTP asynchrone |
| `structlog` | ≥24.1 | Logging structuré JSON |
| `python-ulid` | ≥2.0 | Génération d'IDs ULID (triables par temps) |

**Groupes d'extras (dépendances optionnelles)**

| Groupe | Commande | Ce qu'il ajoute |
|---|---|---|
| `v1` | `pip install -e ".[v1]"` | FastAPI, Uvicorn, Typer, pypdf, docx, BS4, sentence-transformers, openai, anthropic, qdrant-client, rank-bm25, cohere, pymupdf |
| `v3` | `pip install -e ".[v3]"` | neo4j, networkx, spacy, python-louvain (communautés) |
| `v4` | `pip install -e ".[v4]"` | opentelemetry-sdk, opentelemetry-api, opentelemetry-exporter-otlp |
| `v5` | `pip install -e ".[v5]"` | pymupdf, pillow, pytesseract (vision) |
| `dev` | `pip install -e ".[dev]"` | pytest, pytest-asyncio, mypy, ruff, httpx, respx |
| `all` | `pip install -e ".[all]"` | Tout ci-dessus |

**Entry point CLI** : `mrag` → `modular_rag.cli:app` (commande installée dans le PATH)

**Config des outils**
- `pytest` : mode asyncio automatique
- `mypy` : strict + plugin pydantic
- `ruff` : 100 chars par ligne, Python 3.11

---

### `README.md`
Pitch commercial et référence API cible. Sections principales :
- Pourquoi ce framework (tableau comparatif vs. LangChain, LlamaIndex)
- Vision V1→V5 et architecture 6 planes
- Snippets de l'API cible (code décoratif, pas encore exécutable)
- Status pre-alpha + instructions d'installation

---

### `CLAUDE.md`
Instructions architecturales pour Claude Code. Contient :
- État du projet (ce qui est implémenté, ce qui manque)
- Les 7 règles de conventions (contracts first, no cross-domain imports, manifests as source of truth…)
- Les commandes usuelles (pytest, mrag, uvicorn)
- Les workflows Claude Code exposés par `.claude/skills/`
- Le hook qualité post-édition et l'audit de layering
- Info sur le repo GitLab privé Publicis

Voir aussi [`docs/guides/claude-code.md`](../guides/claude-code.md) pour le guide
d'utilisation et de maintenance de cette configuration.

### `AGENTS.md`
Instructions persistantes pour Codex. Définit Codex comme reviewer/challenger
indépendant, décrit les règles de review de diff, les limites d'édition, et la
politique d'escalade par tiers de modèle.

### `.codex/`
Notes projet spécifiques à Codex. Le dossier reste minimal : les règles durables
vivent dans `AGENTS.md`, les workflows détaillés dans `docs/guides/`.

---

### `ROADMAP.md`
Checkboxes de jalons par version. Critères de livraison par version :
- v0.1 → `examples/simple_qa/` end-to-end fonctionnel
- v0.2 → `pip install -e ".[v1]"` + tous les tests unitaires V1 passent
- v1.0 → V1 complète
- v2.0 → V2 complète (agents, routing adaptatif)

---

### `CHANGELOG.md`
Format Keep A Changelog. Section `[Unreleased]` contient tous les ajouts depuis v0.0.1 : implémentation complète du squelette V1→V5, 5 manifests, 3 ADRs, docs architecture, guides, exemples.

---

### `CONTRIBUTING.md`
Guide en 5 étapes pour ajouter un composant (exemple : nouveau chunker) : check contract → implémenter → enregistrer dans `_default_factories.py` → manifest → tests. Checklist MR incluse.

---

### `LICENSE`
Apache License 2.0 — Copyright 2026 Publicis Groupe — Data Specialists. Choix d'Apache 2.0 plutôt que MIT pour la clause brevet explicite (standard enterprise AI/ML).

---

## `src/modular_rag/` — LE PACKAGE PRINCIPAL

Le package suit une **architecture hexagonale** stricte à 13 couches. La règle fondamentale : les dépendances ne coulent que vers le bas (`core/` ne dépend de rien, `contracts/` ne dépend que de `core/`, les modules domaine ne dépendent que de `contracts/` + `core/`).

```
src/modular_rag/
├── __init__.py              → __version__ = "0.0.1"
├── core/                    ← Couche fondatrice — ne dépend de rien
├── contracts/               ← Interfaces (Protocols) — dépend de core/ seulement
├── adapters/                ← Bindings externes — implémente contracts/
├── ingestion/               ← Domaine : fichier → Document → Chunk
├── retrieval/               ← Domaine : Query → list[RetrievedChunk]
├── generation/              ← Domaine : contexte → Answer
├── security/                ← Domaine : filtrage, détection, redaction, policies
├── agents/                  ← Domaine : runtime multi-agents V2
├── memory/                  ← Domaine : graphe de connaissances V3
├── eval/                    ← Domaine : métriques et benchmarks
├── observability/           ← Domaine : télémétrie structurée
├── orchestration/           ← Runtime : engine, registry, router, compiler
├── app/                     ← Wiring process-level : bootstrap, container, settings
├── cli/                     ← Edge : Typer CLI (`mrag ask`, `mrag ingest`)
└── api/                     ← Edge : FastAPI REST API
```

---

### `core/` — La couche fondatrice

**Règle** : `core/` n'importe rien de ce projet. C'est la base de tout.

#### `core/enums.py`

7 enums `StrEnum` (valeurs = chaînes Python, pas des entiers) :

| Enum | Valeurs | Usage |
|---|---|---|
| `Modality` | text, image, table, audio, video, code | Type de contenu d'un Document/Chunk |
| `RetrievalMethod` | vector, bm25, hybrid, graph, multimodal | Comment un RetrievedChunk a été trouvé |
| `ChunkingStrategy` | fixed, sentence, paragraph, section, adaptive, semantic | Stratégie de chunking (dans le manifest) |
| `RoutingStrategy` | llm_only, simple_rag, agentic_rag, graph_rag, multimodal_rag | Stratégie choisie par le Router |
| `PolicyAction` | allow, deny, redact, warn, require_review | Action d'une PolicyRule |
| `AgentRole` | coordinator, planner, retriever, extractor, synthesizer, validator, critic | Rôle d'un agent V2 |
| `GraphRelation` | depends_on, causes, is_part_of, works_for, contradicts, supports, derives_from | Type de relation dans le graphe V3 |


#### `core/ids.py`
- `new_id()` → ULID (Universally Unique Lexicographically Sortable Identifier, basé sur UUID4). Trié par temps de création.
- `short_id()` → 8 premiers caractères du ULID. Utilisé pour les labels lisibles.

#### `core/errors.py`
Hiérarchie complète d'exceptions :

```
ModularRAGError                ← base
├── ConfigurationError         ← manifest ou settings invalide
│   └── ManifestError          ← YAML non chargeable
├── RegistryError              ← composant introuvable dans le registre
├── IngestionError             ← parsing ou chunking échoué
├── IndexingError              ← écriture vector/lexical store échouée
├── RetrievalError             ← retrieval échoué
├── GenerationError            ← appel LLM échoué
├── SecurityError              ← query ou réponse bloquée
│   └── PolicyViolationError   ← policy rule violée
├── EvaluationError            ← scoring ou benchmark échoué
├── GraphError                 ← graphe V3 échoué
├── AgentError                 ← tâche agent V2 échouée
└── StorageError               ← backend storage échoué
```

#### `core/models/` — Les entités du domaine

Tous des `BaseModel` Pydantic v2. Pas d'ORM, pas de DB mapping.

**`document.py` → `Document`** (`frozen=True`)
- Unité atomique d'ingestion. Une fois créé depuis un fichier, son contenu ne change jamais.
- Champs : `id` (ULID auto), `source` (chemin ou URL), `content` (texte brut extrait), `modality`, `mime_type`, `metadata`, `created_at`
- Invariant : `frozen=True` — toute mutation produit une nouvelle instance.

**`chunk.py` → `Chunk`** (`frozen=False`)
- Sous-segment d'un Document. Mutable pour permettre l'écriture de l'embedding après création.
- Champs : `id`, `doc_id` (référence au Document parent), `content`, `modality`, `embedding` (list[float] | None), `start_char`, `end_char`, `page`, `metadata`
- Property calculée : `token_estimate` = `len(content.split())` — approximation, pas stockée.

**`query.py` → `Query`** (`frozen=True`)
- Requête utilisateur immutable. Le texte ne peut pas changer en cours de pipeline (briserait la corrélation avec la Trace).
- Champs : `id`, `text`, `modality`, `routing_hint` (RoutingStrategy optionnel pour forcer une stratégie), `metadata`, `created_at`

**`retrieved.py` → `RetrievedChunk`** (`frozen=True`)
- Chunk enveloppé avec ses métadonnées de retrieval.
- Champs : `chunk` (Chunk), `score` (float 0–1), `rank` (int 1-based), `retrieval_method`
- `__lt__` défini pour permettre `sorted(list_of_retrieved_chunks)` par rank.

**`answer.py` → `Citation` + `Answer`**
- `Citation` : pointeur depuis la réponse vers un chunk source. Champs : `chunk_id`, `source`, `passage` (extrait verbatim, tronqué à 300 chars), `score`, `page`, `metadata`
- `Answer` : texte généré + liste de citations + métadonnées de traçabilité. Champs : `id`, `query_id`, `text`, `citations`, `confidence`, `trace_id`, `model`, `metadata`, `created_at`

**`trace.py` → `TraceStep` + `Trace`**
- `TraceStep` : métriques d'une étape (`name`, `input_tokens`, `output_tokens`, `latency_ms`, `metadata`)
- `Trace` : accumule les steps via `add_step()`. L'appel met à jour atomiquement `total_latency_ms`, `total_input_tokens`, `total_output_tokens`.
- Lié à l'Answer via `Answer.trace_id = trace.id`

**`policy.py` → `PolicyRule` + `Policy`** (V4)
- `PolicyRule` : une règle avec `condition` (expression DSL ou regex), `action` (PolicyAction), `priority` (int)
- `Policy` : groupe de règles scopées à un `tenant` et des pipelines (`scope`). `sorted_rules()` trie par priority décroissante.

**`metrics.py` → `Metrics`**
- Bag plat de scores d'évaluation (tous optionnels). `summary()` retourne uniquement les champs non-None.
- Champs : `recall_at_k`, `precision_at_k`, `ndcg`, `mrr`, `groundedness`, `faithfulness`, `answer_relevance`, `context_precision`, `latency_ms`, `input_tokens`, `output_tokens`, `cost_usd`

---

### `contracts/` — Les interfaces du framework

**Règle** : Tous les `Protocol` sont `@runtime_checkable`. Aucune classe concrète n'hérite de ces Protocols — la conformité est structurelle (duck typing vérifié à l'exécution par `isinstance(obj, Protocol)`).

| Fichier | Protocol(s) exportés | Méthodes clés | Version |
|---|---|---|---|
| `chunking.py` | `Chunker` | `chunk(doc) → list[Chunk]`, `name() → str` | V1 |
| `embeddings.py` | `Embedder` | `embed(texts) → list[list[float]]`, `aembed()`, `dimensions`, `name()` | V1 |
| `retrieval.py` | `Retriever` | `retrieve(query, k) → list[RetrievedChunk]`, `aretrieve()`, `name()` | V1 |
| `generation.py` | `Generator` | `generate(query, context, trace) → Answer`, `agenerate()`, `name()` | V1 |
| `reranking.py` | `Reranker` | `rerank(query, chunks, k) → list[RetrievedChunk]`, `name()` | V1 |
| `security.py` | `SecurityGuard`, `Redactor`, `GuardResult` | `check_query()`, `check_answer()`, `redact()` | V1 |
| `evaluation.py` | `Evaluator` | `evaluate(query, answer, expected, context) → Metrics`, `name()` | V1 |
| `indexing.py` | `Indexer` | `index(chunks) → int`, `delete(ids)`, `clear()`, `name()` | V1 |
| `storage.py` | `Storage` | `put(key, value)`, `get(key)`, `delete(key)`, `exists(key)` | V1 |
| `telemetry.py` | `Telemetry` | `record_trace(trace)`, `record_metrics(metrics)`, `name()` | V1 |
| `planning.py` | `Planner`, `ExecutionPlan`, `ExecutionStep` | `plan(query) → ExecutionPlan` | V2 |
| `agents.py` | `Agent`, `AgentTask`, `AgentResult` | `run(task) → AgentResult`, `arun()`, `role()`, `name()` | V2 |
| `manifests.py` | `ManifestLoader`, `PipelineManifest`, `ComponentConfig` | `load(path) → PipelineManifest` | V1 |

**`PipelineManifest`** est le schéma complet d'un manifest YAML. Il contient des `ComponentConfig` pour chaque rôle (chunker, embedder, indexer, retriever, reranker, generator, guard, evaluator, telemetry) plus des sections optionnelles V2 (planner, agents), V3 (graph_store), V4 (policies), V5 (modalities).

---

### `adapters/` — Bindings externes

**Rôle** : Isoler les dépendances lourdes externes. Un test de `BM25Retriever` ne doit pas avoir besoin de `sentence-transformers` installé.

#### `adapters/embeddings/`

**`openai_embedder.py` → `OpenAIEmbedder`**
- Implémente `Embedder`. Lazy import de `openai`.
- Init : `model` (ex: `text-embedding-3-small`), `api_key`, `batch_size=64`
- `embed()` : batche les textes, appelle l'API synchrone
- `aembed()` : utilise `AsyncOpenAI`
- `dimensions` : property retournant la taille du vecteur depuis un dict `_DIMENSIONS`

**`hf_embedder.py` → `HuggingFaceEmbedder`**
- Implémente `Embedder`. Lazy import de `sentence-transformers`.
- Init : `model="BAAI/bge-small-en-v1.5"`, `batch_size=32`, `device="cpu"`
- `_get_model()` : chargement lazy du `SentenceTransformer`
- `aembed()` : utilise `asyncio.run_in_executor` (thread pool, car sentence-transformers est synchrone)

#### `adapters/vectorstores/`

**`qdrant_store.py` → `QdrantStore`**
- Implémente `Indexer` + retriever bas niveau. Lazy import de `qdrant-client`.
- `_ensure_collection()` : crée la collection Qdrant si elle n'existe pas (distance cosine)
- `index(chunks)` : upsert des `PointStruct` avec vecteur + payload complet
- `retrieve_by_vector(vector, k)` : `client.search()` → reconstruit des `Chunk` depuis le payload
- `retrieve()` : lève `NotImplementedError` — le retriever complet nécessite un `Embedder` branché

#### `adapters/llms/`, `adapters/auth/`, `adapters/graphstores/`, `adapters/search/`
**État actuel** : `.gitkeep` uniquement. Placeholders pour :
- `adapters/llms/` : générateurs OpenAI/Anthropic en tant qu'adapters (actuellement dans `generation/`)
- `adapters/auth/` : validation API key / OAuth
- `adapters/graphstores/` : Neo4j (actuellement KnowledgeGraph est in-memory dans `memory/`)
- `adapters/search/` : outils de recherche web (Tavily, Brave…)

---

### `ingestion/` — Pipeline de traitement documentaire

**Flux** : `Fichier → Parser → TextNormalizer → MetadataEnricher → Chunker → list[Chunk]`

#### `ingestion/parsers/`

**`text_parser.py` → `TextParser`**
- Supporte : `.txt`, `.md`, `.rst`
- `supports(path) → bool`, `parse(path) → Document` — lecture UTF-8 avec remplacement des erreurs

**`pdf_parser.py` → `PDFParser`**
- Supporte : `.pdf`
- Lazy import de `fitz` (PyMuPDF, dans le groupe `v1`)
- `parse(path) → Document` — joint les pages avec `\n\n`, ajoute `page_count` en metadata

#### `ingestion/normalizers/`

**`text_normalizer.py` → `TextNormalizer`**
- `normalize(doc) → Document` (nouvelle instance — Document est frozen)
- Opérations : normalisation NFKC unicode, collapse 3+ newlines → 2, collapse 2+ espaces → 1, strip

#### `ingestion/enrichers/`

**`metadata_enricher.py` → `MetadataEnricher`**
- `enrich(doc) → Document` (nouvelle instance)
- Ajoute dans les metadata : `filename`, `extension`, `size_bytes`, `enriched_at`

#### `ingestion/chunkers/`

**`fixed.py` → `FixedSizeChunker`**
- Init : `chunk_size=512` (tokens), `chunk_overlap=64`
- Fenêtre glissante sur les mots. Tracks `start_char` / `end_char` dans le document original.
- `name()` → `"fixed-size"`

**`adaptive.py` → `AdaptiveChunker`**
- Init : `chunk_size=512`, `chunk_overlap=64`
- Coupe d'abord sur les titres Markdown (`#` à `######`) et les doubles newlines (regex)
- Sections trop grandes → re-découpe avec logique fixe
- `name()` → `"adaptive"`

#### `ingestion/pipelines/default.py`

**`ingest_path(path, chunker) → list[Chunk]`**
- Détecte le parser approprié (TextParser ou PDFParser)
- Applique : parser → normalizer → enricher → chunker

**`ingest_directory(directory, chunker) → list[Chunk]`**
- Parcourt récursivement le répertoire, appelle `ingest_path` sur chaque fichier supporté

---

### `retrieval/` — Moteur de recherche

#### `retrieval/retrievers/`

**`bm25.py` → `BM25Retriever`**
- Implémente `Retriever`. Lazy import de `rank-bm25`. Index in-memory.
- `index(chunks)` : reconstruit l'index BM25 sur les nouvelles chunks
- `retrieve(query, k)` : tokenise la query, appelle `BM25Okapi.get_scores()`, filtre scores > 0
- `name()` → `"bm25"`

**`vector.py` → `VectorRetriever`**
- Implémente `Retriever`. Wrappeur générique d'un vector store injecté + `Embedder`.
- `retrieve()` : embed la query via `_embedder`, puis appelle `_store.retrieve_by_vector(query_vec, k)`.
- `_embedder` et `_store` sont injectés par `orchestration/registry.py`; le retriever n'instancie pas d'adapter directement.
- `name()` → `"vector"`

**`hybrid.py` → `HybridRetriever`**
- Combine `VectorRetriever` + `BM25Retriever` via RRF
- Init : `vector_weight=0.7`, `bm25_weight=0.3`, `rrf_k=60`, `k=20`
- `name()` → `"hybrid"`

#### `retrieval/fusion/rrf.py`

**`reciprocal_rank_fusion(lists, k, rrf_k=60) → list[RetrievedChunk]`**
- Fonction pure. Formule : `score(d) = Σ 1 / (rrf_k + rank_i(d))`
- Déduplique par `chunk.id`, limite à `k` résultats, ré-numérote les rangs de 1 à N

#### `retrieval/rerankers/`

**`cross_encoder.py` → `CrossEncoderReranker`**
- Lazy import de `sentence-transformers`. Model par défaut : `cross-encoder/ms-marco-MiniLM-L-6-v2`
- `rerank(query, chunks, k)` : paire (query.text, chunk.content) → `model.predict()` → sort par score

#### `retrieval/planners/`

**`simple.py` → `SimplePlanner`** : Plan fixe [retrieve → rerank → generate] pour V1 (SIMPLE_RAG)

**`graph.py` → `GraphPlanner`** : Plan [entity_extract → graph_retrieve → vector_retrieve → generate] pour V3 (GRAPH_RAG)

---

### `generation/` — Synthèse de réponses

#### `generation/synthesizers/`

**`openai_gen.py` → `OpenAIGenerator`**
- Implémente `Generator`. Lazy import de `openai`.
- Init : `model="gpt-4o-mini"`, `temperature=0.1`, `max_tokens=2048`, `api_key=""`
- `generate(query, context, trace)` : construit un prompt numéroté [1], [2]…, appelle l'API, construit les citations, émet un `TraceStep` avec les token counts
- `agenerate()` : version async

**`anthropic_gen.py` → `AnthropicGenerator`**
- Implémente `Generator`. Lazy import de `anthropic`.
- Init : `model="claude-opus-4-7"`, `max_tokens=2048`, `api_key=""`
- Même logique que OpenAIGenerator mais via l'API Anthropic Messages

#### `generation/citations/builder.py`

**`build_citations(chunks) → list[Citation]`** : Fonction pure. Crée une `Citation` par chunk, tronque le `passage` à 300 chars.

#### `generation/validators/groundedness.py`

**`GroundednessValidator`** : `validate(answer, context) → float [0,1]` — ratio de tokens de la réponse présents dans le contexte (intersection d'ensembles de mots, case-insensitive).

---

### `security/` — Défense en profondeur

#### `security/filters/`

**`basic_guard.py` → `BasicSecurityGuard`** (V1)
- Implémente `SecurityGuard`. Init : `max_query_length=4000`
- 4 patterns regex d'injection : `ignore * instructions`, `disregard * prompt`, `you are now | pretend`, `jailbreak | DAN mode`
- `frozenset` de termes bloqués : `rm -rf`, `os.system`, `exec(`, `__import__`
- `risk_score` : 0.9 (injection) | 0.8 (blocked term) | 0.5 (trop long) | 0.0 (OK)
- `check_answer()` : pass-through en V1 (always allowed)

#### `security/detectors/`

**`adversarial.py` → `AdversarialDetector`** (V2)
- Patterns : `send to email/slack/webhook`, `output all documents`, `base64/curl` exfiltration
- `risk_score` = 0.95 pour l'exfiltration

#### `security/redaction/`

**`patterns.py` → `PatternRedactor`**
- Implémente `Redactor`. 4 patterns de PII → `[REDACTED]` :
  - `email` : `\b[A-Za-z0-9._%+-]+@...\b`
  - `phone_fr` : `\b0[1-9](?:[\s.-]?\d{2}){4}\b`
  - `iban` : `\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}...\b`
  - `api_key` : `\b(?:sk|pk|api|token)[-_][A-Za-z0-9]{20,}\b`

#### `security/policies/`

**`policy_engine.py` → `PolicyEngine`** (V4)
- Init : `policies: list[Policy]`
- `enforce_query(query)` : filtre les policies activées, évalue les règles par priorité décroissante
- DENY → `raise PolicyViolationError` ; WARN → log + allow
- `_evaluate()` : matching par mots-clés (extensible vers CEL/OPA Rego)

---

### `agents/` — Runtime multi-agents (V2)

**`agents/coordinator/coordinator.py` → `CoordinatorAgent`**
- Init : `agents: dict[AgentRole, Agent]`
- `execute_plan(plan, query)` : itère les steps de l'`ExecutionPlan`, dispatch chaque step à l'agent par rôle/nom

**`agents/retriever/retriever_agent.py` → `RetrieverAgent`** : Adapte `Retriever` en tant que `Agent`. Init : `retriever: Retriever`, `k: int = 10`

**`agents/extractor/extractor.py` → `ExtractorAgent`** : Extraction d'entités nommées par regex. Déduplique, limite à 30 entités uniques.

**`agents/synthesizer/synthesizer.py` → `SynthesizerAgent`** : Concatène les top-5 chunks de contexte. Limite le draft à 2000 chars.

**`agents/validator/validator.py` → `ValidatorAgent`** : Calcule un score local de groundedness par overlap de tokens. Ajoute un warning si score < 0.05.

---

### `memory/` — Mémoire persistante (V3)

**`memory/kv/in_memory.py` → `InMemoryStorage`** : Implémente `Storage`. Dict Python simple. Non thread-safe, pour dev/tests uniquement.

**`memory/graph/knowledge_graph.py` → `GraphNode` + `GraphEdge` + `KnowledgeGraph`**
- `GraphNode` : id, label, type, properties, source_chunk_ids
- `GraphEdge` : source_id, target_id, relation (GraphRelation), weight, properties
- `KnowledgeGraph` :
  - `add_node()`, `add_edge()`, `get_node()`
  - `neighbours(node_id, hops)` : BFS pour N sauts
  - `subgraph_for_query(entity_labels, hops)` : seed depuis les labels → expansion BFS
  - `stats()` : {nodes, edges}
- Backend in-memory, swappable avec l'adapter Neo4j (futur)

**`memory/versioning/graph_versioning.py` → `GraphVersionManager`** (EvoRAG)
- `reinforce(source_id, target_id, delta=0.1)` : augmente le poids d'un edge (feedback positif)
- `weaken(source_id, target_id, delta=0.1)` : diminue le poids (feedback négatif)
- `prune(min_weight=0.1)` : supprime les edges sous le seuil
- Bounds : weight ∈ [0.0, 1.0]

---

### `eval/` — Évaluation

**`eval/scorers/exact_match.py` → `ExactMatchEvaluator`**
- Implémente `Evaluator`. Précision/Rappel/F1 sur les ensembles de tokens. Case-insensitive.
- Si `expected=None`, retourne `Metrics` avec `None` scores. `name()` → `"exact-match"`

**`eval/scorers/retrieval_metrics.py`** : Fonctions pures `recall_at_k()`, `precision_at_k()`, `mrr()`. `compute_retrieval_metrics()` les agrège en un seul `Metrics`.

**`eval/runners/benchmark.py` → `BenchmarkCase` + `BenchmarkReport` + `BenchmarkRunner`**
- `BenchmarkCase` : question, expected_answer, relevant_chunk_ids
- `BenchmarkRunner.run(cases)` : parcourt les cas, appelle un `AnswerEngine` compatible (`answer()`), calcule les métriques
- `BenchmarkReport` : metrics_per_case + `avg_answer_relevance`, `avg_recall`

---

### `observability/`

**`StructlogTelemetry`** : Implémente `Telemetry`. Logs JSON structurés via structlog.

**`NullTelemetry`** : Implémente `Telemetry`. No-op pour les tests (zéro overhead).

---

### `orchestration/` — Moteur de runtime

#### `orchestration/engine.py` → `RAGEngine`

Le chef d'orchestre principal. Utilise le Container pour accéder à tous les composants.

**`ingest(documents)`** :
1. Embed les chunks avec `container.embedder.embed()`
2. Index avec `container.indexer.index()`
3. Si le retriever est BM25 : `retriever.index(chunks)` aussi

**`answer(question, **kwargs)`** :
1. Crée `Query` + `Trace`
2. `guard.check_query(query)` → `SecurityError` si refusé
3. `retriever.retrieve(query, k=20)`
4. `reranker.rerank(query, chunks, k=5)` (si configuré)
5. `generator.generate(query, context, trace)`
6. `guard.check_answer(answer)` (si configuré)
7. `telemetry.record_trace(trace)` (si configuré)

**`retrieve(question, k)`** : Retrieval seul, sans generation.

#### `orchestration/_default_factories.py`
Lazy factory callables pour tous les composants built-in. `register_defaults(reg)` est appelée par `ComponentRegistry.default()`.

#### `orchestration/registry.py` → `ComponentRegistry`
Mappe `(role, type_name)` → `factory callable`.
- `register(role, type_name, factory)` : ajoute une factory
- `wire(manifest) → Container` : pour chaque rôle du manifest, appelle `factory(config)`, stocke dans le Container
- `default()` : classmethod qui pré-charge `_default_factories`

#### `orchestration/router.py` → `QueryRouter`
Classifie chaque query en `RoutingStrategy` :
- `routing_hint` sur la Query → override direct
- Mots-clés graphe → `GRAPH_RAG`
- Mots-clés agentiques OU >40 mots → `AGENTIC_RAG`
- <5 mots → `LLM_ONLY`
- Sinon → `SIMPLE_RAG`

#### `orchestration/flow_compiler.py` → `FlowCompiler`
`compile(query, strategy) → ExecutionPlan` avec des templates de steps :
- **LLM_ONLY** : [generate]
- **SIMPLE_RAG** : [retrieve → rerank → generate]
- **AGENTIC_RAG** : [plan → retrieve_agent → synthesizer_agent → validator_agent → output]
- **GRAPH_RAG** : [graph_retrieve → retrieve → generate]

#### `orchestration/state_machine.py` → `PipelineStateMachine`
États : `IDLE → GUARDING_QUERY → RETRIEVING → RERANKING → GENERATING → GUARDING_ANSWER → EVALUATING → DONE` (+ `ERROR`)
Matrice de transitions hard-codée. `transition(to)` valide et log chaque changement d'état.

---

### `app/` — Wiring process-level

#### `app/settings.py` → `Settings`
Pydantic-settings avec préfixe `MRAG_`. Lit depuis `.env` + variables d'environnement.

```
MRAG_OPENAI_API_KEY, MRAG_ANTHROPIC_API_KEY
MRAG_LLM_MODEL, MRAG_TEMPERATURE, MRAG_MAX_TOKENS
MRAG_EMBEDDING_MODEL, MRAG_EMBEDDING_BATCH_SIZE
MRAG_QDRANT_URL, MRAG_QDRANT_API_KEY, MRAG_QDRANT_COLLECTION
MRAG_K, MRAG_RERANKER_K, MRAG_VECTOR_WEIGHT, MRAG_BM25_WEIGHT
MRAG_CHUNK_SIZE, MRAG_CHUNK_OVERLAP
MRAG_SECURITY_ENABLED
MRAG_TELEMETRY_ENABLED, MRAG_OTEL_ENDPOINT, MRAG_LOG_LEVEL
MRAG_NEO4J_URL, MRAG_NEO4J_USER, MRAG_NEO4J_PASSWORD
```

`get_settings()` : singleton (une seule lecture du `.env` par processus).

#### `app/container.py` → `Container`
DI Container. `_store: dict[str, Any]` interne.
- `register(name, component)` : stocke une instance
- Properties typées : `container.chunker`, `container.embedder`, `container.retriever`… Retournent `None` pour les composants optionnels non configurés.

#### `app/bootstrap.py`
- `load_manifest(path) → PipelineManifest` : lit le YAML, valide via Pydantic
- `load_pipeline(path) → RAGEngine` : `load_manifest` → `ComponentRegistry.default()` → `registry.wire(manifest)` → `RAGEngine(container)`

#### `app/lifecycle.py`
- `startup(container)` + `shutdown(container)` : hooks de démarrage/arrêt (actuellement juste du logging — placeholder pour gérer connexions DB, nettoyage, etc.)

---

### `cli/` — Interface ligne de commande

**`cli/__init__.py`** → `app` (instance Typer, entry point `mrag`)

Commandes :
- `mrag ingest <path> --manifest <yaml>` : charge le pipeline, ingère les documents, affiche le nombre indexé
- `mrag ask "<question>" --manifest <yaml>` : charge le pipeline, pose la question, affiche la réponse + citations formatées avec scores
- `mrag version` : affiche `__version__`

---

### `api/` — API REST

**`api/__init__.py`** → `create_app(manifest_path) → FastAPI`

Factory pattern. Endpoints :
- `GET /health` → `{"status": "ok", "pipeline": "<manifest_id>"}`
- `POST /answer` (body: `QuestionRequest{question, k}`) → `AnswerResponse{text, citations, trace_id}`
- `GET /retrieve?q=<question>&k=<n>` → `[{chunk_id, score, content_preview}]`

Codes d'erreur : 403 (SecurityError), 422 (validation Pydantic), 500 (erreurs internes).

---

## `tests/` — Suite de tests

```
tests/
├── __init__.py
├── unit/                    ← Rapides, aucun service externe requis
│   ├── core/test_models.py
│   ├── ingestion/
│   │   ├── chunkers/test_fixed.py
│   │   ├── chunkers/test_adaptive.py
│   │   └── test_normalizer.py
│   ├── retrieval/test_rrf.py
│   ├── security/
│   │   ├── test_basic_guard.py
│   │   └── test_redaction.py
│   ├── eval/test_exact_match.py
│   └── memory/test_knowledge_graph.py
├── contract/                ← Vérifient qu'une implémentation satisfait son Protocol
│   ├── test_chunker_conformance.py      (FixedSizeChunker + AdaptiveChunker)
│   ├── test_retrieval_conformance.py    (BM25Retriever — VectorRetriever exclut Qdrant)
│   ├── test_security_conformance.py     (BasicSecurityGuard + PatternRedactor)
│   └── test_eval_conformance.py         (ExactMatchEvaluator)
├── integration/             ← Requièrent Qdrant sur localhost:6333 (vides actuellement)
├── e2e/                     ← Pipeline complet avec LLM réel (vides actuellement)
├── benchmark/               ← Benchmarks de performance (vides actuellement)
└── fixtures/                ← Fixtures partagées (vides actuellement)
```

**Tests unitaires — détail par fichier**

| Fichier | Ce qui est testé | Cas |
|---|---|---|
| `test_models.py` | Document frozen, Chunk token_estimate, Query frozen, RetrievedChunk __lt__, Trace.add_step accumulation, Metrics.summary, Policy.sorted_rules | 30+ |
| `test_fixed.py` | Court texte → 1 chunk, long texte → N chunks, overlap, doc_id, start_char/end_char, doc vide | 8 |
| `test_adaptive.py` | Coupe sur headings Markdown, doc_id, texte plat, doc vide | 6 |
| `test_normalizer.py` | Collapse newlines, collapse espaces, strip, préserve sémantique, retourne Document | 5 |
| `test_rrf.py` | Une liste préserve l'ordre, déduplication par chunk.id, boost shared doc, limite k, listes vides, re-numérotation | 7 |
| `test_basic_guard.py` | Requête bénigne, injection bloquée, jailbreak bloqué, longueur max | 7 |
| `test_redaction.py` | Email, multiple emails, phone FR, texte bénin inchangé, clé API | 5 |
| `test_exact_match.py` | Correspondance parfaite, aucun overlap, partial overlap, case-insensitive, expected=None | 6 |
| `test_knowledge_graph.py` | add/get node, nœud inexistant → None, add_edge + neighbours, hops, stats(), subgraph_for_query | 8 |

**Tests de conformité — logique**
- `isinstance(obj, Protocol)` → vérifie la conformité structurelle au runtime
- Tests paramétrés sur toutes les implémentations d'un même Protocol
- VectorRetriever et HybridRetriever **exclus** des tests contract (nécessitent Qdrant)

---

## `docs/` — Documentation

```
docs/
├── adr/
│   ├── 0001-modular-architecture.md   ← 6 planes, règle de dépendance
│   ├── 0002-contracts-and-plugins.md  ← Protocol vs ABC, factory registry
│   └── 0003-security-and-governance.md ← Safety vs Security, plan layered
├── api/
│   └── rest.md                  ← Référence REST (endpoints, schémas, codes d'erreur)
├── architecture/
│   ├── overview.md              ← Cahier technique V1→V5, 6 planes, contrats, wiring, RRF, erreurs
│   ├── data-model.md            ← Tous les modèles Pydantic, champs, invariants, lifecycle
│   ├── module-model.md          ← Arbre des modules, règles de dépendance, pattern adapter
│   ├── runtime-flow.md          ← Séquences Mermaid V1 (query + ingestion + data lifecycle), V2, V3
│   ├── security.md              ← Surfaces d'attaque, guard chain, regex patterns, PII types, risk_score
│   ├── structure.md             ← Ce fichier — explication exhaustive de toute la structure
│   └── roadmap-mermaid.md       ← 5 diagrammes Mermaid (timeline, dépendances, wiring V1, V2, V3)
├── guides/
│   ├── getting-started.md       ← Walkthrough en 5 étapes : Qdrant → API key → ingest → ask
│   ├── installation.md          ← Prérequis, extras groupes, Qdrant Docker, variables d'env
│   ├── deployment.md            ← Dockerfile, docker-compose, multi-env manifests
│   ├── observability.md         ← StructlogTelemetry JSON, NullTelemetry, custom adapter
│   └── plugin-development.md    ← Recette 4 étapes pour ajouter un composant
└── reviews/
    └── 2026-05-20-initial-review.md ← Review initiale (forces, faiblesses, décisions P0/P1)
```

---

## `manifests/` — Configurations YAML

```
manifests/
├── presets/
│   ├── local-hybrid-rag.yaml         ← V1 dev local (HuggingFace + Qdrant localhost + GPT-4o-mini)
│   ├── secure-enterprise-rag.yaml    ← V1 prod (guard + policies + GPT-4o, temp=0.0)
│   ├── agentic-rag.yaml              ← V2 (5 agents + coordinator + routing adaptatif)
│   ├── graph-memory-rag.yaml         ← V3 (GraphPlanner + NetworkX + EvoRAG feedback)
│   └── multimodal-rag.yaml           ← V5 (CLIP + Whisper + claude-opus-4-7 + modality agents)
├── dev/                              ← Overrides d'environnement dev (V4, vides actuellement)
├── staging/                          ← Overrides staging (V4, vides actuellement)
└── production/                       ← Overrides production (V4, vides actuellement)
```

| Manifest | Version | LLM | Embedder | Sécurité | Particularité |
|---|---|---|---|---|---|
| `local-hybrid-rag` | V1 | gpt-4o-mini | bge-small-en-v1.5 | aucune | Développement, Qdrant localhost |
| `secure-enterprise-rag` | V1 | gpt-4o | bge-base-en-v1.5 | BasicSecurityGuard + policies | max_query_length=2000, temp=0.0 |
| `agentic-rag` | V2 | gpt-4o | bge-base-en-v1.5 | BasicSecurityGuard | k=30, rerank_k=10, 5 agents |
| `graph-memory-rag` | V3 | gpt-4o | bge-base-en-v1.5 | BasicSecurityGuard | GraphPlanner, EvoRAG feedback |
| `multimodal-rag` | V5 | claude-opus-4-7 | CLIP + bge-base | BasicSecurityGuard | multi-vector, modality agents |

---

## `examples/` — Applications exemples

```
examples/
├── simple_qa/                    ← Seul exemple complet (V1)
│   ├── main.py                   ← CLI argparse : ingest + ask
│   ├── README.md                 ← Prérequis, 4 étapes, features démontrées
│   └── docs/
│       ├── rag-overview.md       ← Document d'exemple sur le RAG (Lewis 2020, variantes)
│       └── retrieval-methods.md  ← Document d'exemple sur dense/BM25/hybrid/reranking
├── agentic_rag/                  ← Placeholder V2
├── graph_memory/                 ← Placeholder V3
├── hybrid_search/                ← Placeholder V1 variante
└── secure_rag/                   ← Placeholder V1 sécurisé
```

**`examples/simple_qa/main.py`** — Le script de référence :

```python
# Ingestion
pipeline = load_pipeline("manifests/presets/local-hybrid-rag.yaml")
chunks = ingest_directory("./docs", AdaptiveChunker())
pipeline.ingest(chunks)

# Question
answer = pipeline.answer("What is RAG?")
print(answer.text)
for c in answer.citations:
    print(f"  [{c.source}] score={c.score:.3f} — {c.passage[:80]}…")
```

---

## Roadmap d'implémentation par version

| Version | Thème | État | Ce qu'il reste |
|---|---|---|---|
| **V1** | Core RAG | ~95% | Stabiliser tests integration/e2e, `adapters/llms/` à remplir |
| **V2** | Agentic | ~100% code | Tests E2E avec vrai LLM, `examples/agentic_rag/` |
| **V3** | Graph Memory | ~80% | `adapters/graphstores/neo4j_store.py`, NER spaCy, communautés Louvain, `examples/graph_memory/` |
| **V4** | Governance | ~60% | Évaluation CEL/OPA Rego, audit trail, human-in-the-loop, manifests env-specific |
| **V5** | Multimodal | ~5% | Modules entiers à créer (`multimodal/`, `vision/`, `tables/`, `audio/`), adapters CLIP/Whisper |

---

## Principes architecturaux récapitulatifs

| Règle | Pourquoi |
|---|---|
| **Contracts first** | Avant toute implémentation concrète, le Protocol existe et est testé |
| **No cross-domain imports** | Un retriever ne peut pas importer depuis `generation/` — isolation des tests sans LLM |
| **Manifests as source of truth** | Un composant n'est "activé" que s'il est dans le YAML — pas de wiring Python caché |
| **Tests mirror src/** | `tests/unit/ingestion/chunkers/test_fixed.py` pour `src/modular_rag/ingestion/chunkers/fixed.py` |
| **ADR before structural changes** | Tout nouveau layer ou contract requiert un ADR sous `docs/adr/` |
| **Observability is mandatory** | Toute méthode de retrieval/generation/agent émet une `Trace` |
| **Safety ≠ Security** | Safety (injection, PII) dans `security/filters/` et `security/redaction/` ; Security (RBAC, policies) dans `security/policies/` |
