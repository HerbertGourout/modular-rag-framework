# Onboarding — Profils fonctionnels et parcours complet du framework

> Ce document répond à une question simple mais qui n'avait pas de réponse unique dans le
> dépôt : **qui doit lire quoi, dans quel ordre, et pourquoi** — que vous soyez développeur,
> lead technique, consultant en mission client, product owner fonctionnel, ou responsable
> sécurité/conformité. Il complète [`docs/business-case.md`](business-case.md) (le "pourquoi
> commercial") et [`ROADMAP.md`](../ROADMAP.md) (le "quoi, coché au fur et à mesure") en
> répondant au "qui fait quoi, et comment s'y retrouver".

---

## 1. Pourquoi ce document existe

Le framework a grossi vite : cinq versions planifiées (V1 à V5), une trentaine de fichiers
de documentation, des ADR, des manifests, une architecture hexagonale à treize couches. Un
nouvel arrivant — qu'il vienne coder ou qu'il vienne comprendre ce que l'outil permet de
faire pour un client — se retrouve devant une quantité d'information qui n'indique pas par
où commencer. Ce document trace ce chemin.

Il ne remplace aucun document existant : il **indexe et contextualise**. Chaque section
renvoie vers le document source qui fait autorité sur le sujet.

---

## 2. Les profils qui interagissent avec le framework

Le framework n'a pas un seul type d'utilisateur. Chaque profil ci-dessous a des besoins et
un niveau de profondeur technique différents. Comprendre à quel profil vous appartenez (ou
pour lequel vous écrivez) évite de lire 700 lignes de spécification Pydantic quand une seule
page de manifest YAML suffirait.

### 2.1 Développeur du framework (contribue au code source)

Construit ou étend les composants internes : un nouveau chunker, un nouveau retriever, un
nouveau générateur, une nouvelle policy. Ce profil touche à `src/modular_rag/`, écrit des
tests, et doit respecter la règle de dépendance hexagonale (`core/` → `contracts/` →
domaines → `orchestration/` → `app/` → `cli/`/`api/`).

**Ce que ce profil doit lire, dans l'ordre :**
1. [CLAUDE.md](../CLAUDE.md) — les règles non négociables (contracts first, pas d'import
   croisé entre domaines, manifests comme source de vérité).
2. [CONTRIBUTING.md](../CONTRIBUTING.md) — setup local, recette pas-à-pas pour ajouter un
   composant.
3. [docs/architecture/module-model.md](architecture/module-model.md) — pourquoi la règle de
   dépendance existe, avec des exemples concrets de ce qu'elle empêche.
4. [docs/architecture/data-model.md](architecture/data-model.md) — les objets Pydantic qui
   circulent partout (`Document`, `Chunk`, `Query`, `Answer`, `Trace`…).
5. [docs/guides/plugin-development.md](guides/plugin-development.md) — la recette en quatre
   étapes (contrat → implémentation → registre → manifest).
6. Les ADR ([docs/adr/](adr/)) pertinents pour la zone qu'il modifie.

Ce profil ne doit **jamais** avoir besoin de lire `docs/business-case.md` pour faire son
travail — mais le lire une fois aide à comprendre pourquoi certaines contraintes
(gouvernance V4, souveraineté des données) sont non négociables même quand elles compliquent
l'implémentation.

### 2.2 Lead technique / architecte

Décide des évolutions structurelles : nouveau layer, nouveau contrat, changement de
frontière entre modules. Écrit ou valide les ADR. Arbitre entre "on étend un contrat
existant" et "on en crée un nouveau".

**Lecture prioritaire :**
1. [docs/architecture/overview.md](architecture/overview.md) — la spécification technique
   complète, les six plans du système, la roadmap V1→V5 avec le détail de ce que chaque
   version ajoute.
2. [docs/adr/](adr/) — les trois décisions déjà actées (six plans, Protocol + registry,
   safety vs security) et le gabarit à suivre pour une nouvelle décision.
3. [docs/architecture/module-model.md](architecture/module-model.md) et
   [structure.md](architecture/structure.md) — la carte complète du code, fichier par
   fichier.
4. [docs/reviews/2026-05-20-initial-review.md](reviews/2026-05-20-initial-review.md) — la
   revue initiale qui a posé les priorités P0/P1/P2 ; utile pour comprendre pourquoi certains
   choix (Apache 2.0, statut pre-alpha honnête, tests miroir de `src/`) ont été tranchés tôt.

### 2.3 Consultant / delivery lead sur un projet client

Configure un pipeline pour un client via les manifests YAML, sans nécessairement modifier de
code Python. Doit savoir quel preset choisir, comment l'adapter (modèle LLM, niveau de
sécurité, profondeur de retrieval), et comment démontrer une preuve de concept rapidement.

**Lecture prioritaire :**
1. [docs/guides/getting-started.md](guides/getting-started.md) — du clone à la première
   réponse, en cinq étapes.
2. [manifests/_index.md](../manifests/_index.md) — quel preset choisir selon le contexte
   client (dev local, entreprise sécurisée, agentique, graphe, multimodal).
3. [docs/guides/installation.md](guides/installation.md) — variables d'environnement,
   dépendances par version.
4. [docs/guides/deployment.md](guides/deployment.md) — comment faire tourner ça en dehors
   d'un poste de dev (Docker, multi-environnement).
5. [docs/business-case.md](business-case.md) — les arguments à réutiliser face à un client
   (économie de 4-8 semaines, gouvernance by design, indépendance vendor).

Ce profil n'a normalement pas besoin de lire `data-model.md` ni `module-model.md` — sauf s'il
doit expliquer à un DSI client *pourquoi* l'architecture est fiable.

### 2.4 Profil fonctionnel / product owner / business analyst

Ne code pas, ne configure pas nécessairement les manifests, mais doit savoir **ce que
l'outil permet de faire aujourd'hui, ce qu'il permettra de faire demain**, pour cadrer un
besoin client ou une user story. C'est le profil le plus souvent oublié dans une
documentation technique — d'où l'existence de ce document.

**Lecture prioritaire :**
1. La section 3 ci-dessous (« Le parcours complet, expliqué sans jargon technique »).
2. [docs/business-case.md](business-case.md) — le cas d'usage business complet : ROI,
   positionnement concurrentiel, couverture réglementaire.
3. [ROADMAP.md](../ROADMAP.md) — ce qui est déjà livré (case cochée) versus ce qui reste à
   construire, par version.
4. [examples/simple_qa/docs/rag-overview.md](../examples/simple_qa/docs/rag-overview.md) —
   une explication non technique de ce qu'est le RAG et pourquoi ça existe, utile pour
   vulgariser face à un client qui ne connaît pas le terme.

Ce profil n'a besoin d'aucun fichier sous `src/modular_rag/`, ni des ADR (trop techniques),
ni de `module-model.md`. S'il a besoin de connaître une capacité précise ("est-ce qu'on peut
déjà répondre sur une vidéo ?"), la réponse est dans le tableau de version de la section 3 —
pas dans le code.

### 2.5 Sécurité / conformité (RSSI, DPO, auditeur)

Doit évaluer si le framework respecte les contraintes réglementaires (RGPD, DORA, NIS2,
sectorielles) avant qu'un client régulé ne l'adopte. Ne code pas, mais a besoin de preuves
concrètes — pas de promesses marketing.

**Lecture prioritaire :**
1. [docs/architecture/security.md](architecture/security.md) — les surfaces d'attaque
   couvertes, la chaîne de garde-fous, les patterns de redaction PII exacts (regex, types de
   données couvertes).
2. [docs/adr/0003-security-and-governance.md](adr/0003-security-and-governance.md) — la
   séparation Safety (anti-injection, PII) vs Security (RBAC, policies), et ce qui est déjà
   implémenté (V1) versus prévu (V4).
3. [docs/business-case.md](business-case.md), section 4 — couverture des industries
   régulées, argumentaire pour un DPO ou un RSSI côté client.

**Point de vigilance à communiquer à ce profil sans détour** : au statut actuel, la
gouvernance policy-as-code, le multi-tenant et l'audit trail complet sont des items **V4,
non encore livrés** (voir [ROADMAP.md](../ROADMAP.md)). Ne jamais présenter ces capacités
comme déjà opérationnelles face à un client ou un auditeur — c'est le type d'écart entre
promesse documentaire et code livré que la revue initiale du 2026-05-20 a explicitement
signalé comme risque n°1 du projet (voir
[docs/reviews/2026-05-20-initial-review.md](reviews/2026-05-20-initial-review.md)).

### 2.6 Management / commercial

N'a besoin que de [docs/business-case.md](business-case.md) et du tableau de statut du
[README.md](../README.md) ("Project status"). Rien d'autre n'est nécessaire à ce niveau.

---

## 3. Le parcours complet, expliqué sans jargon technique

Cette section répond à la question "qu'est-ce que ce framework va faire, du début à la
fin ?" en langage clair, sans supposer de connaissance de l'architecture. Chaque version
n'est pas un module isolé : elle dépend de la précédente et il n'existe pas de raccourci
(vous ne pouvez pas sauter à la V3 sans que la V1 fonctionne, parce que le graphe de
connaissances V3 s'appuie sur le pipeline de retrieval déjà construit en V1).

### V1 — Core RAG : répondre à une question à partir de documents

**Le problème résolu.** Un client a des documents (PDF, Word, pages web, notes internes) et
veut poser des questions en langage naturel et obtenir une réponse sourcée, plutôt que de
chercher manuellement dans des dizaines de fichiers.

**Comment ça marche, en une phrase.** Les documents sont découpés en petits morceaux
("chunks"), indexés de deux façons complémentaires (une recherche par sens et une recherche
par mots-clés), et à chaque question, les morceaux les plus pertinents sont retrouvés puis
donnés à un modèle de langage (GPT ou Claude) qui rédige une réponse en citant ses sources.

**Pourquoi deux méthodes de recherche combinées et pas une seule ?** La recherche par sens
("vectorielle") comprend les paraphrases et les synonymes mais peut rater un acronyme
technique exact ("SLA", "IBAN") que l'utilisateur tape mot pour mot. La recherche par
mots-clés (BM25) fait l'inverse : parfaite sur les termes exacts, aveugle aux paraphrases.
Combiner les deux (fusion RRF, détaillée dans
[docs/architecture/overview.md](architecture/overview.md), section 11) donne le meilleur des
deux mondes sans sacrifice.

**État** : ✅ terminé et fonctionnel de bout en bout — voir `examples/simple_qa/`.

### V2 — Agentic : des questions qui demandent plusieurs étapes de raisonnement

**Le problème résolu.** V1 fonctionne bien pour "quel est le chiffre d'affaires du Q3 ?"
mais échoue sur "compare les résultats du Q3 aux prévisions initiales et explique l'écart" —
une question qui demande de récupérer plusieurs informations, de les croiser, puis de
vérifier que la réponse est bien étayée avant de la donner.

**Comment ça marche.** Un routeur détecte qu'une question est complexe et la confie à une
équipe de cinq agents spécialisés plutôt qu'à un seul appel de modèle : un planificateur
découpe la question en étapes, un agent récupère l'information, un agent extrait les faits
pertinents, un agent rédige un brouillon, un agent valide que le brouillon est bien étayé par
les sources — et si ce n'est pas le cas, la boucle recommence la recherche avant de rendre la
réponse finale.

**État** : ⬜ planifié — voir [ROADMAP.md](../ROADMAP.md).

### V3 — Graph Memory : comprendre les relations entre les informations, pas seulement leur contenu

**Le problème résolu.** V1 et V2 retrouvent des morceaux de texte pertinents, mais ne
"savent" pas que "Client X" est lié contractuellement à "Fournisseur Y", qui a eu un
incident affectant "Projet Z". Ce type de question à sauts multiples ("qui est concerné, en
cascade, par l'incident chez Y ?") demande un graphe de connaissances, pas juste une
recherche de texte.

**Comment ça marche.** Le corpus est analysé pour en extraire les entités (personnes,
organisations, projets) et leurs relations, construisant un graphe. À la question, le
framework part des entités mentionnées, explore le graphe à N sauts, et injecte ce
sous-graphe comme contexte structuré en plus des chunks de texte classiques. Un mécanisme de
retour d'expérience (EvoRAG) renforce ou affaiblit les relations du graphe selon que les
réponses basées dessus se sont avérées correctes ou non.

**État** : ⬜ planifié — voir [ROADMAP.md](../ROADMAP.md).

### V4 — Governance : rendre le système utilisable dans un contexte réglementé, à grande échelle

**Le problème résolu.** Un déploiement interne à une seule équipe n'a pas besoin de
gouvernance formelle. Un déploiement chez une banque, un assureur, ou pour plusieurs clients
sur la même instance en a besoin absolument : qui a le droit de voir quelles données,
comment prouver à un régulateur que telle réponse n'a pas fuité de PII, comment isoler
complètement les données d'un client de celles d'un autre.

**Comment ça marche.** Des règles de gouvernance sont écrites en YAML ("policy-as-code"),
versionnées dans Git comme du code, et appliquées automatiquement à chaque requête et
chaque action d'agent. Chaque tenant (client, business unit) a ses propres règles et ses
propres données, sans risque de contamination croisée. Chaque décision de sécurité est
journalisée pour audit. Les réponses jugées à risque peuvent être mises en attente de
validation humaine avant d'être renvoyées.

**État** : ⬜ planifié — voir [ROADMAP.md](../ROADMAP.md). C'est la version qui déverrouille
les projets clients dans les secteurs régulés (voir
[docs/business-case.md](business-case.md), section 4).

### V5 — Multimodal : au-delà du texte

**Le problème résolu.** Beaucoup de documents utiles ne sont pas du texte pur : un rapport
financier a des graphiques, un contrat a des tableaux, une réunion a un enregistrement audio.
V1 à V4 ne traitent que le texte extrait de ces documents — perdant l'information contenue
dans une image ou un tableau.

**Comment ça marche.** Des parseurs spécialisés extraient les images, tableaux, transcriptions
audio et segments vidéo. Chaque modalité a son propre agent spécialisé, et l'index vectoriel
devient multi-vecteur (texte + image + tableau). Les réponses peuvent citer directement une
image, un passage de tableau ou un timecode vidéo comme preuve.

**État** : ⬜ planifié, l'implémentation la moins avancée à ce jour — voir
[ROADMAP.md](../ROADMAP.md).

---

## 4. Comment le plan de développement se met à jour

Trois documents, à des granularités différentes, se mettent à jour à chaque évolution :

| Document | Granularité | Se met à jour quand |
|---|---|---|
| [ROADMAP.md](../ROADMAP.md) | Case à cocher par fonctionnalité, par version | Une fonctionnalité listée est livrée et validée par ses tests |
| [CHANGELOG.md](../CHANGELOG.md) | Entrée narrative par changement notable | À chaque Merge Request, sous la section `[Unreleased]` (règle imposée par la checklist de MR dans [CONTRIBUTING.md](../CONTRIBUTING.md)) |
| [README.md](../README.md), section "Project status" | Vue d'ensemble à plat, par composant | Quand un composant majeur change de statut (✅/⬜) |

Il n'existe pas de mécanisme automatique : la mise à jour de ces trois fichiers fait partie
de la checklist de Merge Request. C'est une discipline d'équipe, pas un outil — si une MR
ferme un item de la roadmap sans cocher la case correspondante, la roadmap devient
silencieusement fausse. Voir [CONTRIBUTING.md](../CONTRIBUTING.md), section "Merge Request
checklist".

Pour visualiser la même roadmap sous forme de diagrammes (frise chronologique, graphes de
dépendance), voir [docs/architecture/roadmap-mermaid.md](architecture/roadmap-mermaid.md).

---

## 5. Ce qui n'existe pas encore et qu'il ne faut pas promettre

Pour éviter de reproduire l'écart identifié dans la revue du 2026-05-20 (documentation qui
annonce des capacités non livrées), voici l'état honnête au moment de la rédaction de ce
document :

- Tout ce qui est V2 à V5 dans la section 3 est **planifié, pas livré**. Le code peut déjà
  exister partiellement (voir le tableau "Roadmap d'implémentation par version" dans
  [docs/architecture/structure.md](architecture/structure.md)), mais "code écrit" ne veut
  pas dire "testé end-to-end et démontrable en clientèle".
- `adapters/llms/`, `adapters/auth/`, `adapters/graphstores/`, `adapters/search/` sont des
  placeholders vides (voir [CLAUDE.md](../CLAUDE.md), section 09).
- `tests/integration/` et `tests/e2e/` existent mais nécessitent des services externes
  (Qdrant, clé API LLM) pour s'exécuter.
- `manifests/dev/`, `manifests/staging/`, `manifests/production/` sont des stubs V4 — voir
  [manifests/_index.md](../manifests/_index.md).

Avant toute présentation client ou tout engagement contractuel sur une capacité, vérifier son
statut dans [ROADMAP.md](../ROADMAP.md) plutôt que de se fier à la mémoire ou à une
conversation précédente — la roadmap change plus vite que les habitudes.
