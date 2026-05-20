# Évaluation initiale — Structure du projet & README

**Date :** 2026-05-20
**Auteur :** Évaluation collaborative (Herbert + Claude)
**Cible :** `modular-rag-framework` au commit `47a519d` (branche `initial-structure`)

---

## Contexte

Cahier technique très ambitieux pour un framework RAG modulaire open-source avec un plan de release en 5 versions (V1 RAG core → V5 Multimodal, en passant par agentic, graph memory, gouvernance). Cette revue porte sur l'état du dépôt et du README en regard de cette vision.

**État réel du dépôt observé** : c'est un **scaffold structurel complet mais vide**. 108 lignes au total dans le repo, **toutes localisées dans le `README.md`**. Tous les fichiers Python, YAML manifests, et docs (.md d'architecture, ADR, guides) sont à 0 ligne. Le dernier commit est explicite : *"Add initial project structure, README"*.

L'évaluation porte donc sur la **qualité du squelette comme fondation** et sur la **qualité éditoriale du README**, pas sur du code existant.

---

## 1. Avis global

**Verdict : très bon scaffold, ambitieux et cohérent — mais à ce stade c'est uniquement une promesse architecturale. Le README sur-vend ce qui existe réellement.**

Le squelette de répertoires reflète fidèlement le cahier technique : séparation control plane / ingestion / knowledge / reasoning / safety / evaluation. La granularité des modules (contracts, core, orchestration, ingestion, retrieval, generation, agents, security, memory, eval, observability, adapters, cli, api) est exactement ce qu'on attend d'un framework qui veut séparer interfaces et implémentations.

**Le risque principal** : le README parle au présent ("Adaptive chunking", "Hybrid retrieval", "Agentic runtime", `pipeline.answer(...)`) alors qu'aucune ligne de code n'existe. Pour un projet open-source, c'est un signal de défiance — un visiteur qui clone et tape `pip install -e .` sur le `pyproject.toml` vide aura une mauvaise première impression.

> ✅ **Action prise le 2026-05-20** : le README a été refondu pour annoncer honnêtement le statut pre-alpha, ajouter un "Why this framework?", trancher la licence à Apache 2.0, et marquer les exemples comme "target API — not functional yet". Cf. section 7.

---

## 2. Forces de la structure actuelle

### 2.1 Découpage `contracts/` séparé des implémentations
Avoir [src/modular_rag/contracts/](../../src/modular_rag/contracts/) (chunking, embeddings, indexing, retrieval, reranking, generation, planning, agents, security, evaluation, storage, telemetry, manifests) **isolé du reste** est exactement la bonne décision pour un framework modulaire. C'est ce qui rend les composants remplaçables.

### 2.2 Couche `adapters/` distincte
[src/modular_rag/adapters/](../../src/modular_rag/adapters/) (auth, embeddings, graphstores, llms, search, vectorstores) sépare clairement les intégrations externes du noyau. Bon pattern hexagonal.

### 2.3 Manifests par environnement
[manifests/dev/](../../manifests/dev/), [manifests/staging/](../../manifests/staging/), [manifests/production/](../../manifests/production/) + [manifests/presets/](../../manifests/presets/) anticipe la V4 (gouvernance multi-environnement) dès la V1. Excellent.

### 2.4 Presets alignés sur la roadmap
Les 5 presets ([local-hybrid-rag.yaml](../../manifests/presets/local-hybrid-rag.yaml), [secure-enterprise-rag.yaml](../../manifests/presets/secure-enterprise-rag.yaml), [agentic-rag.yaml](../../manifests/presets/agentic-rag.yaml), [graph-memory-rag.yaml](../../manifests/presets/graph-memory-rag.yaml), [multimodal-rag.yaml](../../manifests/presets/multimodal-rag.yaml)) tracent visuellement le chemin V1→V5. C'est un excellent contrat avec la roadmap.

### 2.5 Tests stratifiés
[tests/unit/](../../tests/unit/), [tests/integration/](../../tests/integration/), [tests/e2e/](../../tests/e2e/), [tests/contract/](../../tests/contract/), [tests/benchmark/](../../tests/benchmark/) — la présence d'un dossier `contract/` montre que vous avez compris l'enjeu : les contracts doivent avoir des **tests qui vérifient que les implémentations respectent l'interface**. C'est mature.

### 2.6 ADR + benchmarks dès le départ
[docs/adr/](../adr/) (Architecture Decision Records numérotés) et [benchmarks/](../../benchmarks/) (configs, datasets, notebooks, results) sont des signaux forts de qualité. Beaucoup de projets RAG les ajoutent trop tard.

### 2.7 Agents granulaires
[agents/coordinator/](../../src/modular_rag/agents/coordinator/), [extractor/](../../src/modular_rag/agents/extractor/), [retriever/](../../src/modular_rag/agents/retriever/), [synthesizer/](../../src/modular_rag/agents/synthesizer/), [validator/](../../src/modular_rag/agents/validator/) — correspond exactement aux rôles définis dans la V2 (planner/retrieval/synthesis/critic/output).

### 2.8 Memory avec graph + versioning
[memory/graph/](../../src/modular_rag/memory/graph/), [memory/kv/](../../src/modular_rag/memory/kv/), [memory/versioning/](../../src/modular_rag/memory/versioning/) anticipe V3 (GraphRAG) et V4 (change management). La présence de `versioning/` est particulièrement astucieuse.

---

## 3. Faiblesses et points de vigilance

### 3.1 ❌ Tout est vide — le README ment par omission
Toutes les promesses concrètes du README (`pipeline = load_pipeline(...)`, `pipeline.answer(...)`, examples `simple_qa`/`hybrid_search`/etc.) ne fonctionneront pas. Le `pyproject.toml` est vide → `pip install -e .` échouera.

✅ **Résolu le 2026-05-20** par la refonte du README (encart pre-alpha explicite).

### 3.2 ❌ Aucun `tests/` par module
Vous avez les **catégories** de tests (unit/integration/e2e/contract) mais aucun fichier dedans, et **aucune structure miroir** de `src/modular_rag/`. Quand des centaines de modules vont apparaître, retrouver le test d'un composant deviendra douloureux. Préparer dès maintenant `tests/unit/contracts/`, `tests/unit/orchestration/`, etc. (en miroir de `src/`) éviterait une refonte plus tard.

### 3.3 ❌ Pas de `examples/` exécutables ni de `pyproject.toml` minimal
Les 5 dossiers `examples/` n'ont que des `.gitkeep`. Pour un projet open-source, **l'expérience "git clone → exemple qui tourne en 60 secondes"** est décisive pour l'adoption. Sans ça, le projet aura du mal à attirer des contributeurs.

### 3.4 ⚠️ Couplage `core/models/` ↔ `contracts/` à clarifier
[core/models/](../../src/modular_rag/core/models/) contient `document, chunk, query, retrieved, answer, trace, policy, metrics`. C'est très proche de ce qui devrait être référencé par [contracts/](../../src/modular_rag/contracts/). Une ADR explicite (ADR-0004 ?) sur la frontière core/contracts éviterait du couplage circulaire plus tard.

### 3.5 ⚠️ `app/` vs `orchestration/` — frontière ambiguë
[app/](../../src/modular_rag/app/) (bootstrap, container, settings, lifecycle) et [orchestration/](../../src/modular_rag/orchestration/) (engine, registry, router, flow_compiler, state_machine) se chevauchent conceptuellement. Sans documentation, un contributeur ne saura pas où mettre quoi. À clarifier dans une ADR ou dans `docs/architecture/module-model.md` (actuellement vide).

### 3.6 ⚠️ Mention `pscode.lioncloud.net` dans un projet "open-source"
Le README annonce "open-source" mais les badges et l'URL de clone pointent vers une instance GitLab privée (Publicis). Soit le projet est **interne** (et "open-source" est trompeur), soit il y aura un mirroring public à prévoir. À trancher rapidement — ça impacte la licence, la CI, les templates d'issues.

### 3.7 ⚠️ Aucune trace de l'aspect multimodal dans `src/`
La V5 multimodal est mentionnée dans la roadmap et a son preset, mais il n'y a aucun module `multimodal/`, `vision/`, `tables/`, `audio/` sous `src/modular_rag/`. Ce n'est pas forcément un problème (vous l'ajouterez en V5), mais à mentionner explicitement comme "deferred" dans une ADR pour éviter la confusion.

### 3.8 ⚠️ `safety plane` du cahier technique non visible
Le cahier technique mentionne 6 plans : control / ingestion / knowledge / reasoning / **safety** / evaluation. Le dépôt a [security/](../../src/modular_rag/security/) (detectors, filters, policies, redaction) mais pas de séparation explicite entre `safety` (anti-prompt-injection, anti-poisoning) et `security` (RBAC, ACL). Pour la V4 gouvernance, ces deux concerns sont distincts et mériteraient peut-être deux modules.

---

## 4. Évaluation du README (avant refonte)

### Points forts
- **Vision claire** ("context OS for RAG and agentic systems") — bonne phrase d'accroche.
- **Mermaid V1→V5** : pédagogique et synthétique.
- **Sections classiques** présentes (Table of Contents, Architecture, Getting started, Roadmap, Contributing, License).
- **Bullet de features** lisible.

### Points faibles (résolus le 2026-05-20)
- ✅ **Tense problem** : tout au présent alors que rien n'existe → encart pre-alpha ajouté.
- ✅ **Pas de status badge** → badge `status: pre-alpha` ajouté.
- ✅ **Exemple de code factice** sans avertissement → marqué `# Roadmap snippet — not functional yet`.
- ✅ **License "MIT (or another license to be defined)"** → tranchée à Apache 2.0.
- ✅ **Pas de "Why this framework?"** → section ajoutée avec comparatif LangChain/LlamaIndex/Haystack.
- ✅ **Pas de lien vers la vision détaillée** → lien vers `docs/architecture/overview.md` ajouté.
- ⚠️ **Mélange français/anglais dans le projet** (README en anglais, mais cahier technique en français) — à harmoniser ou à offrir en bilingue. *Non encore résolu.*

---

## 5. Recommandations priorisées

### P0 (à faire avant d'inviter le 1er contributeur)
1. ✅ **Ajouter un encart "status pre-alpha"** en haut du README. *(Fait le 2026-05-20.)*
2. ⬜ **Remplir `pyproject.toml`** au minimum (nom, version 0.0.0, python_requires, dependencies vides).
3. ✅ **Trancher la licence** (Apache 2.0 retenue, à appliquer dans le fichier `LICENSE`). *(Décidé le 2026-05-20 ; fichier `LICENSE` à mettre à jour séparément.)*
4. ⬜ **Clarifier "open-source vs internal Publicis"** : si privé, retirer "open-source" du README ; si public, prévoir un miroir GitHub.

### P1 (les 2 premières semaines)
5. ⬜ **Écrire au moins 3 ADR remplies** : `0001-modular-architecture`, `0002-contracts-and-plugins`, `0003-security-and-governance`.
6. ⬜ **Implémenter 1 exemple end-to-end** (`examples/simple_qa/`) qui tourne réellement, même avec un LLM mocké. C'est le critère #1 d'adoption.
7. ⬜ **Définir et documenter les `contracts/`** (au moins `retrieval.py`, `generation.py`, `chunking.py`) — ils gèlent l'interface contractuelle ; tout le reste découle.
8. ⬜ **Verser le cahier technique** dans `docs/architecture/overview.md` (actuellement vide).

### P2 (avant la première release)
9. ⬜ **Mirror `tests/` sur `src/`** (créer `tests/unit/contracts/test_retrieval.py` etc.).
10. ✅ **Ajouter un "Why?" / comparaison** dans le README (LlamaIndex vs LangChain vs ceci). *(Fait le 2026-05-20.)*
11. ⬜ **CI minimale** (`.gitlab-ci.yml` ou GitHub Actions) : lint + test contracts vides + build doc.
12. ⬜ **Trancher la frontière `app/` ↔ `orchestration/`** dans une ADR.

---

## 6. Conclusion

> *La structure est exceptionnellement bien pensée pour un projet RAG modulaire — c'est l'un des squelettes les plus matures qu'on puisse voir à ce stade (séparation contracts/adapters, manifests par environnement, ADR, contract tests, agents granulaires). Mais le README parlait d'un produit qui n'existait pas encore. **L'écart entre l'ambition documentée et le code livré est aujourd'hui le plus grand risque du projet** — pas l'architecture, qui est saine.*

> *Priorité absolue : faire fonctionner **un seul** chemin V1 bout-en-bout (`simple_qa`), même minimal, avant d'élargir. Sinon, vous risquez de construire 5 versions d'API sur le papier sans jamais valider l'API V1 par un usage réel.*

---

## 7. Refonte du `README.md` (appliquée le 2026-05-20)

La refonte du README a été appliquée. Elle :

- déclare honnêtement le statut **pre-alpha** dès le haut,
- ajoute un "Why this framework?" et un positionnement vs LangChain / LlamaIndex / Haystack,
- décale les exemples de code derrière un avertissement (`# Roadmap snippet — not functional yet`),
- ajoute un lien vers le cahier technique (à verser dans `docs/architecture/overview.md`),
- tranche la licence à **Apache 2.0** (article 3 = clause de brevet explicite, essentielle pour un usage entreprise multi-employeurs ; standard de facto des frameworks AI/ML modernes : LangChain, LlamaIndex, Haystack, vLLM, transformers).
- conserve les sections existantes (architecture mermaid V1→V5, roadmap, contributing).

Fichier modifié : [README.md](../../README.md)

---

## 8. Suites à donner

- ⚠️ Mettre à jour le fichier [LICENSE](../../LICENSE) avec le texte officiel Apache 2.0 (sinon le badge du README est mensonger).
- ⚠️ Trancher la mention "open-source" vs GitLab privé (point 3.6).
- ⬜ Reste des items P0/P1/P2 ci-dessus.

---

## Fichiers critiques cités

- README : [README.md](../../README.md) *(refondu le 2026-05-20)*
- À remplir en priorité : [pyproject.toml](../../pyproject.toml), [ROADMAP.md](../../ROADMAP.md), [CHANGELOG.md](../../CHANGELOG.md), [docs/architecture/overview.md](../architecture/overview.md)
- ADR à écrire : [docs/adr/0001-modular-architecture.md](../adr/0001-modular-architecture.md), [docs/adr/0002-contracts-and-plugins.md](../adr/0002-contracts-and-plugins.md), [docs/adr/0003-security-and-governance.md](../adr/0003-security-and-governance.md)
- Contrats à définir en premier : [src/modular_rag/contracts/retrieval.py](../../src/modular_rag/contracts/retrieval.py), [generation.py](../../src/modular_rag/contracts/generation.py), [chunking.py](../../src/modular_rag/contracts/chunking.py)
- Exemple à faire vivre : [examples/simple_qa/](../../examples/simple_qa/)
