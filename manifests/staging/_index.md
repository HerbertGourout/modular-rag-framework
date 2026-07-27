# `manifests/staging/` — Surcharges d'environnement de préproduction (V4, pas encore implémenté)

Ce dossier est un stub, au même titre que [`../dev/`](../dev/) et
[`../production/`](../production/). Aucune surcharge d'environnement n'est encore
implémentée — voir [ROADMAP.md](../../ROADMAP.md), section "V4 — Governance".

**Ce qui est prévu ici** : une configuration qui reflète la production (mêmes garde-fous de
sécurité, mêmes modèles) mais pointant vers des ressources de test — un cluster Qdrant
dédié, une clé API avec quota limité, un tenant de démonstration isolé des données réelles
des clients. L'objectif est de pouvoir valider un changement de manifest ou de policy dans
des conditions proches du réel avant de le promouvoir en production, sans risquer de données
sensibles.

En attendant, dérivez manuellement un manifest à partir de
[`secure-enterprise-rag.yaml`](../presets/secure-enterprise-rag.yaml) en pointant vers vos
ressources de préproduction.
