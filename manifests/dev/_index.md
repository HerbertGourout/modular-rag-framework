# `manifests/dev/` — Surcharges d'environnement de développement (V4, pas encore implémenté)

Ce dossier est un stub. Il n'existe aujourd'hui aucun mécanisme de surcharge
d'environnement — ce sont directement les fichiers de [`../presets/`](../presets/) (en
particulier [`local-hybrid-rag.yaml`](../presets/local-hybrid-rag.yaml)) qui servent de
configuration de développement.

**Ce qui est prévu ici, en V4** (voir [ROADMAP.md](../../ROADMAP.md), section "V4 —
Governance") : un fichier de surcharge appliqué par-dessus un preset de base, activé quand
`MRAG_ENVIRONMENT=dev` (variable documentée dans
[docs/guides/installation.md](../../docs/guides/installation.md)). L'objectif est de
permettre, par exemple, un logging plus verbeux et l'absence d'authentification en local,
sans dupliquer l'intégralité d'un manifest de production.

En attendant cette fonctionnalité, utilisez directement un preset de
[`../presets/`](../presets/) et adaptez-le manuellement si besoin.
