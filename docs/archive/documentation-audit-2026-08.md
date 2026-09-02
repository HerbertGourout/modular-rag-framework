# Audit documentaire complet — Modular RAG Framework

**Date** : 2026-08-06

**Périmètre** : 158 fichiers Markdown réels du dépôt (221 trouvés par le glob, 62 exclus car ce sont des `README.md` de dépendances tierces sous `.venv/`).

**Méthode** : inventaire par répertoire, puis lecture intégrale de chaque fichier (5 lots parallélisés) avec vérification croisée contre le code réel (`src/modular_rag/`, `.claude/settings.json`, `pyproject.toml`, `manifests/`) — pas une estimation, chaque « obsolète » listé ci-dessous a été confirmé par grep/lecture directe du code au moment de l'audit.

**Contexte structurant** : le dépôt vient de terminer un programme de refactoring en 18 lots (2026-08-03 → 2026-08-06) qui a accepté l'[ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) — l'orchestration multi-agents générique et la traversée GraphRAG sont désormais **déléguées** à un moteur externe (LangGraph, ADR-0006), plus construites nativement. La quasi-totalité des obsolescences trouvées ci-dessous sont des reliquats de cette bascule que la passe de réalignement du Lot 2 (2026-08-04) n'a couverte que partiellement.

---

## 1. Inventaire documentaire

| Catégorie | Répertoire | Nb fichiers | Rôle |
|---|---|---|---|
| Landing / racine | `README.md`, `ROADMAP.md`, `CHANGELOG.md` | 3 | Vitrine projet, feuille de route V1-V5, historique des versions |
| Contribution | `CONTRIBUTING.md`, `AGENTS.md`, `.codex/README.md`, `CLAUDE.local.example.md` | 4 | Setup dev, rôle de Codex (reviewer indépendant), template de préférences perso |
| Config Claude Code (racine) | `CLAUDE.md`, `.claude/.instructions.md`, `.claude/.prompt.md`, `.claude/AGENTS.md`, `.claude/project-structure.md` | 5 | Règles non-négociables, style de réponse, catalogue de subagents |
| Règles Claude Code (`.claude/rules/`) | 10 fichiers | 10 | Règles d'édition par module (contracts, orchestration, agents, adapters, sécurité, tests…) |
| Subagents Claude Code (`.claude/agents/`) | 8 fichiers | 8 | Fiches d'experts de domaine (retrieval, generation, sécurité, orchestration…) |
| Skills Claude Code (`.claude/skills/*/SKILL.md`) | 18 fichiers | 18 | Commandes slash (`/qa-v1`, `/add-component`, `/release`…) |
| Guides Claude Code (méta-doc outillage) | `docs/guides/claude-code*.md` | 9 | Comment utiliser Claude Code lui-même sur ce dépôt (hooks, MCP, plugins, settings…) |
| Guides framework | `docs/guides/*.md` (hors claude-code-*) | 19 | Installation, déploiement, backup/restore, observabilité, validation, onboarding… |
| Architecture | `docs/architecture/*.md` | 9 | Vue d'ensemble technique, modèle de données, sécurité, threat model, contrat `DocumentEngine` |
| ADR | `docs/adr/*.md` | 7 (6 ADR + index) | Décisions d'architecture actées |
| Programme de refactoring | `docs/refactoring-plan.md` + `docs/refactoring/*.md` | 23 | Plan, tracker, 20 fiches de décision par lot, guide de lecture |
| Recherche | `docs/research/*.md` | 9 | 7 digests arXiv distillés + catalogue de preuves + index |
| API | `docs/api/*.md` | 2 | Référence REST + index |
| Manifestes | `manifests/*.md` | 5 | Classification runnable/blueprint, index par environnement |
| Exemples | `examples/**/*.md` | 7 | READMEs et docs pédagogiques des deux exemples exécutables |
| CLAUDE.md de module | `src/modular_rag/{contracts,orchestration,security}/CLAUDE.md` | 3 | Règles spécifiques à un sous-module |
| Divers / navigation | `docs/onboarding.md`, `docs/glossary.md`, `docs/business-case.md`, `docs/_index.md`, `docs/guides/_index.md`, `docs/reviews/2026-05-20-initial-review.md` | 6 | Hub de lecture, lexique, argumentaire commercial, revue historique |
| Legacy GitLab | `.gitlab/**/*.md` | 5 | Templates d'issues/MR — **tous vides (0 octet)**, remote GitLab abandonné |
| **Total** | | **158** (147 hors GitLab vide) | |

---

## 2. Diagnostic qualité

### 2.1 Le motif dominant : la bascule ADR-0005 n'a pas été propagée partout

La passe de réalignement (Lot 2, 2026-08-04) a corrigé `CLAUDE.md`, `.claude/.instructions.md`, `.claude/rules/security-layers.md`, `.claude/rules/adapters.md`, et posé des bannières « superseded » sur `.claude/rules/agentic_workflows.md` et `.claude/rules/agents.md`. Mais **elle n'a pas touché** aux fichiers suivants, qui décrivent encore l'orchestration multi-agents native, `QueryRouter`/`FlowCompiler`, ou `EvoRAG`/`GraphVersionManager` comme du code présent ou à construire nativement — **alors que tout ça a été supprimé au Lot 17** (zéro test, zéro consommateur, vérifié avant suppression) :

| Fichier | Nature du problème | Preuve |
|---|---|---|
| `docs/architecture/overview.md` | Tableau des contrats cite `Planner`/`Agent` comme contrats V2 existants | Aucun fichier `contracts/planning.py`/`contracts/agents.py` — supprimés |
| `docs/architecture/runtime-flow.md` | Diagramme complet « V2 Agentic RAG » avec Coordinator/Planner/Retriever Agent/Validator, sans aucune mention de la délégation | Section entière à réécrire |
| `docs/guides/framework-overview-onboarding.md` | Le plus périmé du lot : « Multi-agent runtime (coordinator, planner, retriever, synthesizer, validator) » et « EvoRAG (edge reinforcement) » présentés comme roadmap native, 791 lignes, aucune mention ADR-0005/0006 | Daté juin 2026, jamais retouché |
| `docs/guides/feature-integration-plan.md` | Même défaut, angle commercial (staffing/deal-size sur du multi-agent natif) | Daté 2026-06-20 |
| `docs/guides/getting-started.md`, `docs/guides/validation.md`, `docs/guides/validation-protocol.md`, `docs/guides/troubleshooting.md` | Présentent `MRAG_OPENAI_API_KEY` comme mécanisme de config fonctionnel | Confirmé : `Settings`/`get_settings()` n'est jamais appelé dans le chemin de wiring réel (trouvé Lot 16c) |
| `docs/guides/plugin-development.md` | Tableau des types de composants liste encore `Agent` comme point d'extension natif légitime | `agents/` est désormais un stub adaptateur, pas un type de composant |
| `docs/guides/observability.md` | Exemple JSON de trace inclut `"routing_strategy": "simple_rag"` | `RoutingStrategy` n'existe plus |
| `.claude/project-structure.md` | L'arborescence ASCII en haut du fichier liste encore `agents/ → coordinator, planner…`, `orchestration/ → …QueryRouter, FlowCompiler…` ; une note de correction a été ajoutée en bas **sans que l'arbre du haut soit corrigé** — le fichier se contredit lui-même | Auto-contradiction interne |
| `.claude/rules/orchestration.md` | Sections 3 et 10 documentent `QueryRouter` en détail (avec exemple de test l'instanciant) comme composant V1 vivant | Aucune bannière « superseded », contrairement à ses fichiers-frères `agents.md`/`agentic_workflows.md` |
| `src/modular_rag/orchestration/CLAUDE.md` | **Le plus en décalage de tout l'audit** : « Rule 4 — QueryRouter: Decision Logic » documente le code complet de routage comme s'il existait, table de stratégies incluse | Totalement manqué par la passe Lot 2 |
| `README.md` | Tableau comparatif : « agents: First-class, with planner/retrieval/synth/critic separation » sans réserve | Contredit par `agents/__init__.py` actuel |
| `ROADMAP.md` | Checklist V2.0 liste encore le multi-agent runtime natif comme item à cocher, alors que la bannière du même fichier dit V2.1 est délégué — ambiguïté sur V2.0 | Incohérence interne |
| `manifests/_index.md` | Décrit `agentic-rag.yaml` (« five-agent runtime ») et `graph-memory-rag.yaml` (« EvoRAG feedback ») comme sélectionnables, sans le badge Blueprint que `manifests/README.md` (même dossier !) applique correctement | Deux fichiers du même dossier se contredisent |
| `docs/glossary.md` | Entrées « Agent », « GraphRAG », « Knowledge graph », « Domain module » sans la réserve ADR-0005 — seule l'entrée « EvoRAG » a été corrigée (au Lot 17) | Correction partielle, pas systématique |
| `docs/business-case.md` | Deux affirmations non retouchées par la correction du Lot 5 : « Graph Memory (V3) can model… an asset that appreciates over time » et « Governance… exists in no OSS framework » au présent | Corrections Lot 5 limitées à 2 lignes, pas à tout le fichier |

### 2.2 Doublons confirmés

| Paire | Taux de recouvrement | Verdict |
|---|---|---|
| `docs/guides/validation.md` (386 l.) ↔ `docs/guides/validation-protocol.md` (366 l.) | ~70 % — même tableau CI/CD, mêmes scénarios de validation, même section troubleshooting, wording quasi identique | **Fusionner** : garder `validation-protocol.md` comme référence canonique (mieux structurée : codes de sortie, cibles de perf, markers pytest), y injecter les sections uniques de `validation.md` (Installation, CLI/API, Exemples, Workflows courants), puis retirer `validation.md` ou le réduire à un pointeur |
| `docs/guides/claude-code-complete-development-guide.md` (1511 l.) ↔ `docs/guides/CLAUDE-CODE-COMPLETE-GUIDE.md` (1290 l.) | Pas un doublon texte, mais un doublon **de système** : deux workflows différents et incompatibles pour la même chose (5 phases EXPLORE→DESIGN→IMPLEMENT→VALIDATE→REVIEW vs 6 étapes EXPLORE→PLAN→VALIDATE→IMPLEMENT→VERIFY→DELIVER) | **Fusionner** : garder `CLAUDE-CODE-COMPLETE-GUIDE.md` (mieux corrigé, sert de hub) comme document de gouvernance/process, garder `claude-code-complete-development-guide.md` comme annexe tactique (exemples de code complets), mais **réconcilier le nombre d'étapes** — un seul workflow, pas deux |
| `docs/guides/_index.md` (260 l., dates juin 2026, doublons internes) ↔ `docs/_index.md` (49 l., à jour, cite le programme de refactoring) | Redondance fonctionnelle (même rôle de hub) mais fraîcheur très différente | `docs/guides/_index.md` à réécrire en s'alignant sur le style terse de `docs/_index.md` |
| `docs/adr/0001-modular-architecture.md` (tableau 6 plans) ↔ `docs/architecture/overview.md` §3 | Tableau quasi identique dupliqué | Garder l'ADR comme source, faire pointer `overview.md` vers lui plutôt que de le reproduire |
| `docs/adr/0004-strategic-features-v1-v5.md` (roadmap détaillée) ↔ `docs/architecture/overview.md` §4 | Même contenu roadmap dupliqué | Idem — un seul emplacement source |
| `manifests/_index.md` ↔ `manifests/README.md` | Les deux décrivent le statut runnable/blueprint des presets, mais se contredisent (voir §2.1) | Fusionner en un seul fichier faisant autorité (garder `README.md`, qui est correct) |

### 2.3 Incohérences internes (un même fichier se contredit)

- **`.claude/project-structure.md`** : arbre du haut vs. note de correction en bas.
- **`ROADMAP.md`** : sa propre section « References » cite « ADR-0005 : Cost optimization strategy » et « ADR-0006 : Continuous fine-tuning » — **ce sont les mauvais titres** (le vrai ADR-0005 est le pivot control-plane, le vrai ADR-0006 est la sélection de LangGraph). Le bandeau en haut du même fichier cite pourtant les bons titres.
- **`docs/adr/_index.md`** : ligne 46 dit `Status: Accepted` pour ADR-0004, ligne 136 du même fichier dit « partiellement supersédé par ADR-0005 » — le statut affiché ne reflète pas la note plus bas.
- **`docs/adr/0004-strategic-features-v1-v5.md`** : son propre en-tête dit toujours `Status: Accepted`, alors qu'ADR-0005 demande explicitement qu'il passe à `Superseded (partial) — see ADR-0005` une fois ADR-0005 accepté (c'est le cas depuis le 2026-08-04).
- **`docs/guides/claude-code-parallelization-orchestration.md`** : affirme que la parallélisation est « enabled by default in `.claude/settings.json` » — mais `.claude/settings.json` lui-même contient une note désavouant cette affirmation (`notes.removedFromV1` : clé inventée, jamais lue par Claude Code).
- **`docs/guides/CLAUDE-CODE-COMPLETE-GUIDE.md`** : dit « 6 path-scoped rules » puis en liste 7 juste en dessous ; dit « 13 skills » alors qu'il y en a 18 réellement.
- **`docs/guides/mcp-integrations.md`** : contient une correction datée (« Correction 2026-06-22 ») à l'étape 4, mais les sections Troubleshooting et Approval Template plus bas n'ont pas reçu la même correction et utilisent encore l'ancien format erroné.

### 2.4 Conflation Claude Code / GitHub Copilot (défaut factuel, indépendant de la bascule ADR-0005)

Deux fichiers confondent le produit documenté (Claude Code) avec un produit différent (GitHub Copilot Chat dans VS Code) :
- `.claude/rules/security-layers.md` — Layer 07 : chemin `~/.vscode/extensions/ms-vscode.copilot/session-logs/`.
- `docs/guides/audit-traceability.md` — instructions d'installation « Rechercher : GitHub Copilot Chat ».
- `docs/guides/onboarding-claude-code.md` — mêmes instructions d'installation via l'extension Copilot.

### 2.5 Fichiers vides / à supprimer sans réserve

- `.gitlab/issue_templates/backend-feature.md`, `bug.md`, `feature.md`, `task.md`, `.gitlab/merge_request_templates/default.md` — **5 fichiers, 0 octet chacun**, remote GitLab abandonné, déjà tentative de suppression au Lot 17 bloquée par le système de permissions (pas une décision).

### 2.6 Liens brisés

- `docs/guides/claude-code-settings-reference.md` → pointe vers `./claude-code-memory.md` et `./claude-code-permissions.md`, **aucun des deux n'existe**.

### 2.7 Fichiers vérifiés propres (pas de correction nécessaire)

`docs/architecture/threat-model.md`, `data-classification-policy.md`, `document-engine-contract.md`, `_index.md` ; ADR-0001, 0002, 0003, 0005, 0006 (contenu, pas statut d'index) ; `docs/api/_index.md` ; `docs/refactoring-plan.md` et les 20 fiches `docs/refactoring/lot-*.md` (normal — ce sont les documents produits par l'audit lui-même) ; `.claude/rules/{adapters,contracts,security,tests}.md` ; `.claude/agents/{security-specialist,orchestration-specialist,architecture-reviewer,test-specialist,generation-specialist,ingestion-specialist,observability-expert,retrieval-specialist}.md` ; `.claude/skills/{add-component,qa-v1,release,validate-architecture}.md` (échantillon) ; `manifests/README.md`, `dev/_index.md`, `staging/_index.md` ; `CONTRIBUTING.md` ; root `AGENTS.md` ; `.codex/README.md` ; `CLAUDE.local.example.md` ; `docs/reviews/2026-05-20-initial-review.md` (artefact historique correctement daté) ; les 7 fichiers `examples/**/*.md` ; `src/modular_rag/{contracts,security}/CLAUDE.md` ; `docs/guides/{ai-engineering-workflow,model-routing,adoption-metrics,code-walkthrough,subagents-parallelization}.md` ; `docs/guides/claude-code-advanced-config.md`, `claude-code-plugins-marketplaces.md`.

---

## 3. Analyse de structure

### 3.1 Problèmes de structure actuelle

1. **`docs/guides/` mélange deux publics** : guides sur *le framework RAG* (installation, déploiement, observabilité — 19 fichiers) et guides sur *l'outil Claude Code lui-même* (9 fichiers `claude-code-*.md`). Un développeur cherchant « comment déployer » doit traverser des fichiers sur les hooks Claude Code.
2. **Deux hubs de navigation concurrents et non synchronisés** : `docs/_index.md` (à jour) et `docs/guides/_index.md` (périmé, daté juin 2026).
3. **Deux « guides complets » Claude Code en parallèle**, avec des workflows contradictoires (5 étapes vs 6 étapes) — signe d'une fusion jamais faite entre deux itérations du même document.
4. **`manifests/_index.md` et `manifests/README.md` se chevauchent** sur le même sujet (statut runnable/blueprint) sans qu'un seul ne fasse autorité.
5. **Mélange français/anglais incohérent** : `.claude/rules/{contracts,security,tests}.md` sont en français, le reste de `.claude/rules/` est en anglais ; `manifests/production/_index.md` est en français alors que `dev/_index.md` et `staging/_index.md` sont en anglais.
6. **`docs/refactoring/` (23 fichiers) n'a pas de souci de structure** — c'est le seul répertoire du dépôt organisé de façon strictement chronologique et cohérente (un fichier par lot, README.md comme index) ; il devrait servir de modèle pour la suite plutôt que d'être retouché.

### 3.2 Structure cible proposée

```
docs/
├── _index.md                      (hub principal — garder tel quel, déjà à jour)
├── onboarding.md                  (garder, bannière déjà ajoutée vers refactoring/README.md)
├── glossary.md                    (à corriger, cf. §4)
├── business-case.md               (à corriger, cf. §4)
│
├── guides/                        (RENOMMÉ EN INTENTION : uniquement guides "framework")
│   ├── _index.md                  (RÉÉCRIT — aligné sur docs/_index.md)
│   ├── getting-started.md
│   ├── installation.md
│   ├── deployment.md
│   ├── backup-restore.md
│   ├── observability.md
│   ├── validation-protocol.md     (FUSION : absorbe validation.md)
│   ├── troubleshooting.md
│   ├── plugin-development.md
│   ├── ai-engineering-workflow.md
│   ├── model-routing.md           (garder séparé de ai-engineering-workflow.md
│   │                                malgré le chevauchement — angles différents,
│   │                                juste ajouter des renvois croisés)
│   ├── audit-traceability.md      (à corriger — conflation Copilot)
│   ├── adoption-metrics.md
│   ├── mcp-integrations.md        (à corriger — correction 2026-06-22 à propager)
│   ├── code-walkthrough.md
│   ├── subagents-parallelization.md
│   ├── working-with-agents.md     (déjà banni/marqué historique — garder)
│   └── framework-overview-onboarding.md   (À RÉÉCRIRE ENTIÈREMENT, cf. §4)
│         feature-integration-plan.md → fusionné dedans ou supprimé (doublon
│         commercial du même contenu, cf. §5)
│
├── claude-code/                   (NOUVEAU sous-dossier — sépare l'outillage
│   │                                Claude Code des guides framework)
│   ├── CLAUDE-CODE-COMPLETE-GUIDE.md      (garde le rôle de hub, workflow unifié)
│   ├── claude-code-advanced-config.md
│   ├── claude-code-settings-reference.md  (liens morts à corriger)
│   ├── claude-code-plugins-marketplaces.md
│   ├── claude-code-mcp-setup.md           (section "built-in servers" à corriger/retirer)
│   ├── claude-code-enterprise-deployment.md (à auditer comme les 3 ci-dessus)
│   ├── claude-code-parallelization-orchestration.md (contradiction settings.json à corriger)
│   ├── claude-code.md                     (garder — le plus fiable du lot)
│   └── (claude-code-complete-development-guide.md fusionné dans COMPLETE-GUIDE.md)
│
├── architecture/                  (garder la structure, corriger le contenu — cf. §4)
├── adr/                           (garder — corriger seulement les statuts, cf. §4)
├── api/                           (garder tel quel)
├── research/                      (garder tel quel — déjà propre)
├── refactoring/                   (garder tel quel — déjà propre, modèle à suivre)
└── reviews/                       (garder — archive historique)
```

*(Le déplacement physique vers `docs/claude-code/` est une proposition, pas une obligation — si on préfère ne pas bouger de fichiers pour limiter le nombre de liens à corriger, on peut se contenter d'un préfixe de nommage clair et d'une meilleure séparation dans `docs/guides/_index.md` seul. Voir priorisation §6.)*

---

## 4. Plan de mise à jour

### Corrections à apporter, par thème

**A. Propager la bascule ADR-0005 (le gros du travail)**
- Réécrire `docs/architecture/overview.md` §4 (roadmap) et le tableau de contrats §6 pour refléter la délégation.
- Réécrire `docs/architecture/runtime-flow.md` — soit supprimer les diagrammes V2/V3, soit les bannir comme `roadmap-mermaid.md` l'a déjà fait (bon précédent à réutiliser).
- Réécrire entièrement `docs/guides/framework-overview-onboarding.md` (791 lignes, le plus périmé) et `docs/guides/feature-integration-plan.md`.
- Corriger `docs/guides/getting-started.md`, `validation.md`/`validation-protocol.md`, `troubleshooting.md`, `plugin-development.md`, `observability.md` sur les variables `MRAG_*` et les presets blueprint.
- Réécrire l'arbre ASCII de `.claude/project-structure.md`.
- Ajouter la bannière « superseded » manquante à `.claude/rules/orchestration.md` (sections 3 et 10).
- **Réécrire entièrement `src/modular_rag/orchestration/CLAUDE.md`** — priorité haute, c'est le fichier le plus en décalage de tout l'audit et il est directement dans le chemin de code que les devs consultent.
- Corriger `README.md` (tableau comparatif, section Vision) et `ROADMAP.md` (checklist V2.0 + section References avec les mauvais numéros d'ADR).
- Fusionner/corriger `manifests/_index.md` contre `manifests/README.md`.
- Compléter les entrées « Agent », « GraphRAG », « Knowledge graph », « Domain module » de `docs/glossary.md` avec la même réserve que l'entrée « EvoRAG » (déjà correcte).
- Corriger les deux affirmations non retouchées de `docs/business-case.md` (§3 gouvernance, §8 Graph Memory).

**B. Corriger les statuts d'ADR**
- `docs/adr/0004-strategic-features-v1-v5.md` : en-tête `Status: Accepted` → `Status: Superseded (partial) — see ADR-0005`.
- `docs/adr/_index.md` : aligner la ligne de statut d'ADR-0004 (ligne 46) avec sa propre note plus bas (ligne 136).
- `ROADMAP.md` : corriger la section References (mauvais titres pour ADR-0005/0006).

**C. Corriger la conflation Claude Code / GitHub Copilot**
- `.claude/rules/security-layers.md` Layer 07.
- `docs/guides/audit-traceability.md` section installation.
- `docs/guides/onboarding-claude-code.md` section prérequis.

**D. Corriger les liens morts**
- `docs/guides/claude-code-settings-reference.md` : retirer ou créer les 2 fichiers manquants (`claude-code-memory.md`, `claude-code-permissions.md`).

**E. Propager les corrections déjà faites une fois mais pas partout**
- `docs/guides/mcp-integrations.md` : propager la correction du 2026-06-22 (étape 4) aux sections Troubleshooting/Approval Template.
- `docs/guides/CLAUDE-CODE-COMPLETE-GUIDE.md` : corriger le nombre de skills (13→18), le nombre de règles (« 6 » vs 7 listées), et la fenêtre de permissions adapters/llms|graphstores|search (encore marquée `deny` alors que passée à `ask` depuis le 2026-08-04/05).
- `docs/guides/claude-code-parallelization-orchestration.md` : corriger l'affirmation « enabled by default in settings.json ».

### Ajouts nécessaires

- Une entrée dans `docs/glossary.md` ou `docs/_index.md` pointant vers `docs/refactoring/README.md` (déjà fait pour `docs/onboarding.md`, pas encore pour les deux autres hubs).
- Un renvoi croisé entre `docs/guides/ai-engineering-workflow.md` et `model-routing.md` (chevauchement assumé mais jamais signalé au lecteur).

### Normalisation du ton / format

- Choisir une langue par fichier et s'y tenir — actuellement `.claude/rules/{contracts,security,tests}.md` et `manifests/production/_index.md` sont en français isolé au milieu d'un corpus anglais. Recommandation : soit tout basculer en anglais (cohérent avec le reste du dépôt et avec le code), soit assumer un doublon FR pour les fichiers les plus consultés (mais pas un mélange à l'intérieur d'un même dossier).
- Harmoniser les bannières de type « superseded » : `agentic_workflows.md`, `agents.md`, `working-with-agents.md` ont le bon format (bloc `>` en haut, ton factuel) — le réutiliser mot pour mot comme gabarit pour `orchestration.md`, `orchestration/CLAUDE.md`, `overview.md`, `runtime-flow.md`.
- Harmoniser les dates de mise à jour — plusieurs fichiers portent encore « Last Updated: June 2026 » sans qu'aucune convention n'impose de les maintenir ; soit on les retire (ils se périment plus vite qu'ils ne servent), soit on les rend obligatoires et on les vérifie en CI.

---

## 5. Recommandations de nettoyage

### À supprimer
| Fichier | Raison |
|---|---|
| `.gitlab/issue_templates/*.md` (4) | Vides, remote GitLab abandonné (suppression déjà tentée au Lot 17, bloquée techniquement — pas une nouvelle décision, juste finir le travail) |
| `.gitlab/merge_request_templates/default.md` | Idem |
| `.gitlab-ci.yml` (racine, pas un `.md` mais lié) | Idem, déjà documenté comme bloqué |

### À fusionner
| Fusionner | Dans | Note |
|---|---|---|
| `docs/guides/validation.md` | `docs/guides/validation-protocol.md` | Garder les sections uniques de `validation.md` (Installation, CLI/API, Exemples, Workflows), retirer le reste dupliqué |
| `docs/guides/claude-code-complete-development-guide.md` | `docs/guides/CLAUDE-CODE-COMPLETE-GUIDE.md` | Réconcilier en un seul workflow (pas 5 étapes ici et 6 là) |
| `manifests/_index.md` | `manifests/README.md` | Un seul fichier faisant autorité sur le statut runnable/blueprint |
| `docs/guides/feature-integration-plan.md` | `docs/business-case.md` ou supprimer | Contenu commercial dupliqué et daté, à fusionner ou retirer plutôt que maintenu séparément |
| Tableau des 6 plans (ADR-0001 vs `overview.md` §3) | Garder dans l'ADR, faire pointer `overview.md` | Éviter la double maintenance |
| Roadmap détaillée (ADR-0004 vs `overview.md` §4) | Idem | Idem |

### À conserver tels quels
Tous les fichiers listés en §2.7, plus l'ensemble de `docs/refactoring/` (23 fichiers, déjà propre et modèle de rigueur), `docs/research/*` (déjà propre), `docs/api/*`, `docs/architecture/{threat-model,data-classification-policy,document-engine-contract,_index}.md`.

### À réécrire entièrement
| Fichier | Pourquoi une réécriture et pas un correctif ciblé |
|---|---|
| `docs/guides/framework-overview-onboarding.md` | 791 lignes, le fichier le plus périmé, contenu commercial+technique mélangé, aucune section n'est à jour |
| `src/modular_rag/orchestration/CLAUDE.md` | Documente un composant entièrement supprimé (`QueryRouter`) avec exemples de code — un correctif ciblé laisserait trop de contenu mort |
| `docs/architecture/runtime-flow.md` | Les sections V2/V3 sont des diagrammes complets à base de composants supprimés — plus simple de les remplacer que de les corriger ligne à ligne |
| `docs/guides/_index.md` | Structure et fraîcheur trop éloignées de `docs/_index.md` pour un correctif — à reconstruire sur le même gabarit |

---

## 6. Livrable final

### 6.1 Tableau récapitulatif (vue consolidée)

| Statut | Nombre de fichiers | % du corpus audité |
|---|---|---|
| ✅ Propre, aucune action | ~78 | ~53 % |
| 🟡 Correctif ciblé nécessaire | ~24 | ~16 % |
| 🟠 Fusion recommandée (12 fichiers concernés, 6 paires/groupes) | 12 | ~8 % |
| 🔴 Réécriture complète nécessaire | 4 | ~3 % |
| ⚫ Suppression (vide/obsolète) | 5 | ~3 % |
| ⚠️ Incohérence interne à corriger (peut chevaucher les catégories ci-dessus) | 7 | ~5 % |

*(Le reste du corpus — skills non échantillonnés, quelques fichiers `.claude/agents/` — n'a pas été lu ligne à ligne mais a été spot-check et n'a rien montré d'anormal ; risque résiduel faible mais non nul.)*

### 6.2 Priorisation des actions

**P0 — Bloquant pour la crédibilité de la doc (à faire en premier)**
1. `src/modular_rag/orchestration/CLAUDE.md` — réécriture (le plus consulté par les devs qui touchent ce module)
2. `docs/adr/0004-strategic-features-v1-v5.md` + `docs/adr/_index.md` — corriger le statut (2 lignes, contradiction visible immédiatement par tout auditeur)
3. `ROADMAP.md` — corriger la section References (numéros d'ADR faux, embarrassant si cité publiquement)
4. `.claude/project-structure.md` — corriger l'arbre (auto-contradiction avec sa propre note)

**P1 — Haute visibilité (lu par tout nouvel arrivant)**
5. `README.md` — tableau comparatif + section Vision
6. `docs/guides/getting-started.md` — tableau des presets + variable d'env
7. `docs/guides/framework-overview-onboarding.md` — réécriture complète
8. `manifests/_index.md` ↔ `manifests/README.md` — fusion

**P2 — Cohérence technique**
9. `docs/architecture/overview.md` + `runtime-flow.md`
10. `.claude/rules/orchestration.md` — bannière manquante
11. `docs/glossary.md` — 4 entrées à compléter
12. `docs/guides/validation.md` ↔ `validation-protocol.md` — fusion

**P3 — Qualité/hygiène (pas bloquant, mais facile et rapide)**
13. Suppression des 5 fichiers GitLab vides + finir le blocage de permission
14. Correction Copilot/Claude Code (3 fichiers)
15. Liens morts dans `claude-code-settings-reference.md`
16. Propagation de la correction MCP du 2026-06-22
17. `docs/business-case.md` — 2 affirmations
18. `docs/guides/feature-integration-plan.md` — fusion ou suppression

**P4 — Confort de lecture (peut attendre)**
19. Fusion des deux guides Claude Code complets
20. Séparation `docs/guides/` framework vs. outillage Claude Code
21. Harmonisation FR/EN
22. `docs/guides/_index.md` — réécriture

### 6.3 Checklist d'exécution

```
□ P0.1  Réécrire src/modular_rag/orchestration/CLAUDE.md (retirer QueryRouter)
□ P0.2  Corriger le Status d'ADR-0004 dans le fichier lui-même et dans adr/_index.md
□ P0.3  Corriger ROADMAP.md §References (bons titres ADR-0005/0006)
□ P0.4  Réécrire l'arbre ASCII de .claude/project-structure.md
□ P1.5  Corriger README.md (tableau comparatif + section Vision, ajouter délégation ADR-0005)
□ P1.6  Corriger docs/guides/getting-started.md (presets + MRAG_OPENAI_API_KEY)
□ P1.7  Réécrire docs/guides/framework-overview-onboarding.md
□ P1.8  Fusionner manifests/_index.md dans manifests/README.md (ou l'inverse, un seul doit rester)
□ P2.9  Corriger docs/architecture/overview.md (§4, §6) et runtime-flow.md (sections V2/V3)
□ P2.10 Ajouter la bannière superseded à .claude/rules/orchestration.md
□ P2.11 Compléter docs/glossary.md (Agent, GraphRAG, Knowledge graph, Domain module)
□ P2.12 Fusionner docs/guides/validation.md dans validation-protocol.md
□ P3.13 Supprimer les 5 fichiers .gitlab/*.md vides (+ .gitlab-ci.yml — débloquer la permission)
□ P3.14 Corriger la conflation Copilot/Claude Code (security-layers.md, audit-traceability.md, onboarding-claude-code.md)
□ P3.15 Corriger/retirer les liens morts dans claude-code-settings-reference.md
□ P3.16 Propager la correction MCP 2026-06-22 dans mcp-integrations.md
□ P3.17 Corriger docs/business-case.md (§3, §8)
□ P3.18 Fusionner ou supprimer docs/guides/feature-integration-plan.md
□ P4.19 Fusionner les deux guides Claude Code complets en un seul workflow
□ P4.20 Séparer docs/guides/ (framework) de la doc outillage Claude Code
□ P4.21 Harmoniser FR/EN dans .claude/rules/ et manifests/
□ P4.22 Réécrire docs/guides/_index.md sur le gabarit de docs/_index.md
```

### 6.4 Recommandations concrètes

1. **Ne pas repartir d'un audit périodique manuel** : la cause racine de tout ce rapport est qu'une passe de réalignement (Lot 2) a corrigé un sous-ensemble de fichiers mais rien n'a empêché les autres de dériver. Recommandation : un job CI léger qui grep la présence de chaînes bannies (`QueryRouter`, `RoutingStrategy`, `EvoRAG` sans « removed »/« superseded » à proximité, `secure-enterprise-rag.yaml` sans « blueprint ») dans `docs/**/*.md` et échoue si trouvé — même logique que `scripts/check_licenses.py`/`check_layering.py`, un ratchet plutôt qu'un audit ponctuel.
2. **Un seul hub de navigation, pas trois** (`docs/_index.md`, `docs/guides/_index.md`, `docs/onboarding.md` se chevauchent partiellement) — consolider en gardant `docs/_index.md` comme entrée unique et les deux autres comme sous-pages spécialisées clairement subordonnées.
3. **Le dossier `docs/refactoring/` est le seul exemple de documentation qui a survécu intact à cet audit** (0 fichier à corriger sur 23) — parce qu'il a une convention stricte (un fichier par lot, jamais retouché après coup, un `README.md` central). C'est le gabarit à copier pour tout futur travail doc de cette ampleur.
4. **Le programme de refactoring a lui-même produit ce risque** : en supprimant du code réel (Lot 17) sans repasser sur toute la doc qui en parlait, il a mécaniquement périmé ~24 fichiers d'un coup. Pour tout futur retrait de fonctionnalité, prévoir la recherche documentaire (`grep` du nom de la classe/fichier supprimé dans `docs/`) comme étape systématique du lot, pas comme un audit séparé après coup.
