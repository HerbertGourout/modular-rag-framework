# Architecture — Vue d'ensemble

Ce dossier est la spécification technique du framework : pas "comment configurer un
pipeline" (ça, c'est [../guides/](../guides/)), mais "comment le système est construit et
pourquoi". Si vous cherchez à comprendre le code avant de le modifier, ou à défendre un choix
structurel devant un architecte client, c'est ici que la réponse se trouve — avec, en
complément, le "pourquoi" figé dans les [ADR](../adr/_index.md).

## Comment naviguer selon votre question

| Votre question | Document |
|---|---|
| "Quelle est la vision globale et que fait chaque version V1→V5 ?" | [overview.md](overview.md) |
| "Quels objets de données circulent dans le pipeline, avec quels champs et invariants ?" | [data-model.md](data-model.md) |
| "Quels modules existent, et pourquoi ne peuvent-ils pas s'importer entre eux ?" | [module-model.md](module-model.md) |
| "Que se passe-t-il, étape par étape, quand une requête est traitée ?" | [runtime-flow.md](runtime-flow.md) |
| "Quelles attaques le framework couvre-t-il, et avec quels mécanismes exacts ?" | [security.md](security.md) |
| "Je veux la carte exhaustive de chaque fichier du dépôt, avec son rôle" | [structure.md](structure.md) |
| "Je veux visualiser la roadmap et les flux sous forme de diagrammes" | [roadmap-mermaid.md](roadmap-mermaid.md) |

## Ordre de lecture recommandé pour un nouvel arrivant technique

1. [overview.md](overview.md) — le cadre général, à lire en entier une première fois.
2. [module-model.md](module-model.md) — pour internaliser la règle de dépendance avant de
   toucher au code.
3. [data-model.md](data-model.md) — pour reconnaître les objets qu'on manipule partout
   (`Document`, `Chunk`, `Query`, `Answer`, `Trace`...).
4. [runtime-flow.md](runtime-flow.md) — pour visualiser le trajet complet d'une requête.
5. [security.md](security.md) et [structure.md](structure.md) — en référence, au besoin.

Ce dossier documente l'état **cible** de l'architecture, y compris pour les versions V2 à V5
pas encore livrées. Le statut réel de chaque capacité (livré / en cours / planifié) est dans
[../../ROADMAP.md](../../ROADMAP.md) — ne confondez pas "documenté" et "implémenté".
