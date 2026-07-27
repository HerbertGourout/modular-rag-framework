# Manifests — Configurer un pipeline sans écrire de Python

Un manifest est un fichier YAML qui décrit un pipeline RAG complet : quel chunker, quel
modèle d'embedding, quel store vectoriel, quel retriever, quel reranker, quel générateur,
quel garde-fou de sécurité, quelle télémétrie. C'est la pièce centrale de la philosophie du
framework (voir [CLAUDE.md](../CLAUDE.md), règle 03) : **un composant n'est activé que s'il
est déclaré dans un manifest** — il n'existe aucun câblage caché dans le code Python que la
configuration YAML ne rendrait pas visible.

**Pourquoi ce choix plutôt qu'une configuration Python classique ?** Trois raisons
concrètes :
1. Un lead ou un chef de projet côté client peut lire et modifier un manifest sans jamais
   ouvrir un fichier `.py` — la barrière d'entrée pour ajuster un pipeline tombe à zéro.
2. Changer de fournisseur LLM (passer de GPT-4o à Claude, ou à un modèle on-premise) devient
   un changement d'une seule ligne YAML, jamais une modification de code — argument central
   pour l'indépendance vendor mise en avant dans [docs/business-case.md](../docs/business-case.md).
3. Un manifest versionné dans Git constitue, à lui seul, la documentation vivante de "quel
   pipeline exact tourne pour quel client" — utile en audit ou en debug de régression.

## Comment un manifest devient un pipeline exécutable

Le chemin complet (détaillé dans
[docs/architecture/overview.md](../docs/architecture/overview.md), section 9) est : le YAML
est chargé et validé par `app/bootstrap.py`, puis `orchestration/registry.py` associe chaque
`type:` déclaré à la classe concrète correspondante (via les factories enregistrées dans
`_default_factories.py`), et le résultat est un `Container` d'instances prêtes à l'emploi que
le `RAGEngine` utilise pour répondre aux questions.

## `presets/` — configurations prêtes à l'emploi

| Preset | Version cible | Cas d'usage |
|---|---|---|
| [`local-hybrid-rag.yaml`](presets/local-hybrid-rag.yaml) | V1 | Développement local : pas d'authentification, modèles légers (GPT-4o-mini, bge-small), Qdrant en localhost. Point de départ recommandé pour tout nouveau contributeur ou toute démo rapide. |
| [`secure-enterprise-rag.yaml`](presets/secure-enterprise-rag.yaml) | V1 | Déploiement interne à un client : garde-fous de sécurité activés, `max_query_length` resserré, température de génération à 0 pour des réponses plus déterministes. |
| [`agentic-rag.yaml`](presets/agentic-rag.yaml) | V2 | Questions multi-étapes nécessitant le runtime à cinq agents (coordinateur, planificateur, retriever, extracteur, synthétiseur, validateur). |
| [`graph-memory-rag.yaml`](presets/graph-memory-rag.yaml) | V3 | Raisonnement sur les relations entre entités (GraphRAG), avec retour d'expérience EvoRAG. |
| [`multimodal-rag.yaml`](presets/multimodal-rag.yaml) | V5 | Documents contenant images, tableaux, ou segments audio/vidéo. |

Pour choisir un preset côté mission client, voir aussi
[docs/onboarding.md](../docs/onboarding.md), section 2.3 (profil consultant / delivery lead).

## `dev/`, `staging/`, `production/` — surcharges par environnement

Ces trois dossiers sont des **stubs volontairement vides** à ce stade (portée V4 — voir
[CLAUDE.md](../CLAUDE.md), section 09). L'idée, une fois construite, est de permettre une
surcharge d'un preset par environnement (ex. : `secure-enterprise-rag.yaml` en base, avec un
`production/overrides.yaml` qui resserre encore la sécurité et active l'audit trail complet)
sans dupliquer tout le fichier. Voir chaque sous-dossier pour le détail de ce qui est prévu :
[dev/_index.md](dev/_index.md), [staging/_index.md](staging/_index.md),
[production/_index.md](production/_index.md).
