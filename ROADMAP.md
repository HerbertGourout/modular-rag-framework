# Roadmap

Ce document est **le plan de développement vivant** du framework : il liste, version par
version, chaque fonctionnalité prévue, et la case correspondante est cochée dès que la
fonctionnalité est livrée et couverte par ses tests. Contrairement à
[docs/architecture/overview.md](docs/architecture/overview.md) (qui décrit l'état *cible* de
l'architecture, y compris pour ce qui n'est pas encore construit), ce fichier reflète l'état
*réel* : une case non cochée signifie que la fonctionnalité n'existe pas encore de façon
fiable, même si du code partiel existe déjà quelque part dans `src/`.

**Comment ce document se met à jour** : à chaque Merge Request qui livre une fonctionnalité
listée ici, la case correspondante est cochée dans la même MR — c'est une étape de la
checklist décrite dans [CONTRIBUTING.md](CONTRIBUTING.md). Le
[CHANGELOG.md](CHANGELOG.md) enregistre en parallèle le détail narratif de chaque changement.
Si vous cherchez une explication non technique de ce que chaque version apporte
concrètement, voir [docs/onboarding.md](docs/onboarding.md), section 3.

Les versions ne sont pas des lots indépendants : chacune dépend de la précédente. Le
raisonnement multi-agents de la V2 s'appuie sur le pipeline de retrieval déjà construit en
V1 ; le graphe de connaissances de la V3 vient enrichir ce même retrieval plutôt que le
remplacer ; la gouvernance de la V4 encadre l'exécution des versions précédentes plutôt que
d'ajouter une fonctionnalité de recherche ; et le multimodal de la V5 étend l'ingestion et
les agents déjà en place. Il n'y a donc pas de raccourci possible vers une version avancée
sans que les précédentes soient stables.

---

## V1 — Core RAG `[In design]`

**Ce que cette version résout** : permettre de poser une question en langage naturel sur un
corpus de documents (PDF, Word, HTML, Markdown, texte) et d'obtenir une réponse sourcée,
sans recherche manuelle. C'est la fondation sur laquelle tout le reste s'appuie — aucune
version suivante ne peut être crédible si celle-ci n'est pas fiable de bout en bout.

- [x] Architectural skeleton (contracts, models, orchestration, manifests)
- [ ] Document parsers: PDF, Word, HTML, Markdown, plain text
- [ ] Chunkers: fixed-size, adaptive (section-aware)
- [ ] Hybrid retrieval: vector (Qdrant) + BM25 fusion (RRF)
- [ ] Cross-encoder reranker
- [ ] Generators: OpenAI, Anthropic
- [ ] Basic security guard (injection detection, length check, redaction)
- [ ] Evaluation: exact match F1, recall@k, MRR
- [ ] REST API (FastAPI) + CLI (`mrag ask`, `mrag ingest`)
- [ ] Example: `examples/simple_qa/` end-to-end running
- [ ] Example: `examples/hybrid_search/`
- [ ] `pip install modular-rag[v1]` installs and works

**Critère de "fait"** : `examples/simple_qa/` tourne réellement de bout en bout (ingestion
réelle, retrieval réel, réponse générée par un vrai LLM, pas un mock), et les tests
unitaires + contract passent sans service externe requis pour ces deux catégories.

## V2 — Agentic + Security `[Planned]`

**Ce que cette version résout** : la V1 échoue sur les questions qui demandent plusieurs
étapes de raisonnement (croiser plusieurs informations, vérifier une réponse avant de la
rendre). Un seul appel à un modèle de langage ne suffit pas à décomposer un problème complexe
de façon fiable — cette version introduit une équipe d'agents spécialisés qui se répartissent
les étapes du raisonnement, avec une boucle d'auto-correction si la réponse n'est pas assez
étayée.

- [ ] Adaptive query router (LLM-only / simple / agentic / graph)
- [ ] Multi-agent runtime: coordinator, planner, retriever agent, extractor, synthesizer, validator
- [ ] Multi-step agentic workflow with plan → retrieve → synthesize → critique → refine
- [ ] Agent plan inspection by security guard
- [ ] Example: `examples/agentic_rag/`

**Dépendance à la V1** : le routeur ne remplace jamais le pipeline V1 — il décide, question
par question, si le pipeline simple suffit ou si l'équipe d'agents doit prendre le relais.
Une régression sur le retrieval hybride de la V1 casse donc silencieusement la V2 aussi.

## V3 — Graph Memory `[Planned]`

**Ce que cette version résout** : la V1 et la V2 retrouvent des passages de texte pertinents,
mais ne modélisent pas les relations entre les entités qu'ils contiennent (qui dépend de qui,
qui a causé quoi). Les questions à sauts multiples ("qui est impacté, en cascade, par tel
incident ?") ont besoin d'un graphe de connaissances plutôt que d'une recherche de texte pure.

- [ ] Knowledge graph construction from corpus (spaCy entity extraction)
- [ ] GraphRAG retrieval (sub-graph selection, multi-hop)
- [ ] Community detection (Louvain) + hierarchical summaries
- [ ] Reasoning graph memory (reusable per query type)
- [ ] EvoRAG: edge reinforcement/weakening from user feedback
- [ ] Neo4j adapter for `adapters/graphstores/`
- [ ] Example: `examples/graph_memory/`

**Dépendance aux versions précédentes** : le graphe vient enrichir le contexte donné au
générateur — il ne se substitue jamais à la recherche vectorielle/BM25 de la V1, qui continue
de fournir le texte brut des passages cités en réponse.

## V4 — Governance `[Planned]`

**Ce que cette version résout** : un déploiement interne à une équipe unique n'a pas besoin
de gouvernance formelle, mais un déploiement partagé entre plusieurs clients ou dans un
secteur régulé (banque, assurance, santé) en a besoin absolument — isolation des données par
tenant, preuve d'auditabilité, capacité à mettre une réponse à risque en attente de
validation humaine avant de la renvoyer. C'est la version qui rend le framework éligible aux
appels d'offres de grands comptes régulés (voir [docs/business-case.md](docs/business-case.md),
section 4).

- [ ] Policy-as-code: YAML rules, PolicyEngine, OPA integration
- [ ] Multi-tenant context (per-tenant knowledge base + policies)
- [ ] Multi-environment manifests (dev/staging/prod)
- [ ] Audit trail: structured logs per query, per agent action, per source access
- [ ] Human-in-the-loop: review queue for high-risk answers
- [ ] Risk profile per pipeline
- [ ] Example: `examples/secure_rag/` extended

**Point de vigilance** : tant que cette version n'est pas cochée, ne présentez jamais la
gouvernance multi-tenant ou l'audit trail complet comme opérationnels face à un client ou un
auditeur — voir [docs/onboarding.md](docs/onboarding.md), section 5.

## V5 — Multimodal `[Planned]`

**Ce que cette version résout** : beaucoup de documents utiles ne sont pas du texte pur — un
rapport financier a des graphiques, un contrat a des tableaux, une réunion a un
enregistrement audio. Les versions précédentes ne traitent que le texte extrait de ces
documents, perdant l'information contenue dans une image, un tableau ou une piste audio.

- [ ] Multimodal parsers: image extraction (pymupdf), table extraction, audio transcription (Whisper), video segmentation
- [ ] Multi-vector Qdrant index (text + image + table)
- [ ] MG²-RAG: multi-granularity cross-modal graph
- [ ] Modality-specialised agents: text_agent, vision_agent, table_agent, video_agent
- [ ] VLM generation (Claude vision, GPT-4V)
- [ ] Enriched citations: image references, timecodes
- [ ] Example: multimodal QA on PDF reports with charts

**État d'avancement réel** : c'est la version la moins avancée du projet à ce jour (voir le
tableau d'implémentation dans
[docs/architecture/structure.md](docs/architecture/structure.md)) — les modules dédiés
(`multimodal/`, `vision/`, `tables/`, `audio/`) restent en grande partie à créer.

---

## Milestones

Ces jalons servent de repère à plus haut niveau que les checkboxes ci-dessus — ils marquent
le moment où une version devient "démontrable" plutôt que "en cours de construction".

| Version | Target criteria |
|---|---|
| v0.1 | `examples/simple_qa/` runs end-to-end with a real LLM |
| v0.2 | `pip install modular-rag[v1]` + all V1 checklist done |
| v1.0 | V1 + evaluation benchmark, API, CLI, full docs |
| v2.0 | V2 agentic + adaptive routing working |
| v3.0 | GraphRAG + Neo4j adapter |
| v4.0 | Policy engine + multi-tenant |
| v5.0 | Multimodal ingestion + agents |
