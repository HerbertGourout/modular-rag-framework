# Architecture Decision Records (ADR)

Un ADR documente **une décision structurelle et pourquoi elle a été prise** — pas ce que fait
le code (ça, c'est le rôle de `docs/architecture/`), mais pourquoi il fait ainsi plutôt
qu'autrement, quelles options ont été écartées, et quelles conséquences (positives et
négatives) la décision assume.

**Pourquoi ça compte** : sans ADR, un contributeur qui arrive six mois plus tard et se
demande "pourquoi utilise-t-on `typing.Protocol` plutôt que des classes abstraites ?" n'a
que le code pour deviner la réponse — et le code ne dit jamais pourquoi une alternative a été
rejetée. L'ADR fige cette mémoire.

**Règle du projet** (voir [CLAUDE.md](../../CLAUDE.md), section 07) : tout nouveau module de
premier niveau, toute nouvelle frontière de couche, ou toute modification d'un contrat
existant nécessite un nouvel ADR sous ce dossier. Les ADR 0001 à 0003 sont déjà actés et
réservés — un nouvel ADR commence à 0004.

## ADR actés

| ADR | Décision | Pourquoi elle compte |
|---|---|---|
| [0001](0001-modular-architecture.md) | Six plans fonctionnels (control, ingestion, knowledge, reasoning, safety, evaluation), chacun exposé uniquement via des contrats | C'est la décision qui rend chaque composant remplaçable sans toucher au reste — elle sous-tend toute la règle de dépendance décrite dans `CLAUDE.md` |
| [0002](0002-contracts-and-plugins.md) | Les contrats sont des `typing.Protocol`, pas des classes abstraites ; le câblage se fait par un registre de factories, jamais en dur dans le code | Permet à un manifest YAML de choisir une implémentation sans qu'aucune classe Python n'ait besoin d'hériter de quoi que ce soit — essentiel pour des implémentations tierces |
| [0003](0003-security-and-governance.md) | Séparation stricte Safety (anti-injection, PII) vs Security (RBAC, policies), montée en charge progressive V1→V4 | Évite que la sécurité devienne un fourre-tout non testable ; permet de livrer une version minimale de sécurité en V1 sans bloquer sur la gouvernance complète de V4 |

## Écrire un nouvel ADR

Reprenez le format des trois ADR existants : Status / Date / Authors, puis Context (le
problème et les risques identifiés), Decision (ce qui est choisi, avec des extraits de code
ou de config si utile), Consequences (positives, négatives, mitigations). Un ADR n'est jamais
supprimé même si la décision est plus tard renversée — un nouvel ADR le remplace et
référence l'ancien.
