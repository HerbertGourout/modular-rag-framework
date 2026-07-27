# `manifests/production/` — Surcharges d'environnement de production (V4, pas encore implémenté)

Ce dossier est un stub, au même titre que [`../dev/`](../dev/) et
[`../staging/`](../staging/). Aucune surcharge d'environnement n'est encore implémentée —
voir [ROADMAP.md](../../ROADMAP.md), section "V4 — Governance".

**Ce qui est prévu ici**, une fois la gouvernance V4 construite :
- Activation systématique de tous les garde-fous de sécurité (`BasicSecurityGuard`,
  `PatternRedactor`, `AdversarialDetector`) — aucun étant optionnel en production.
- Chargement du moteur de policies (`PolicyEngine`) avec les règles versionnées de
  l'organisation cliente ou du tenant.
- Isolation multi-tenant stricte : chaque client dispose de ses propres données et de ses
  propres règles, sans possibilité de contamination croisée.
- Audit trail complet : chaque retrieval, génération et décision de sécurité tracée pour un
  DPO ou un auditeur externe (voir [docs/architecture/security.md](../../docs/architecture/security.md)).

**En attendant cette fonctionnalité**, le déploiement en production s'appuie directement sur
[`secure-enterprise-rag.yaml`](../presets/secure-enterprise-rag.yaml), avec les
recommandations de durcissement listées dans
[docs/guides/deployment.md](../../docs/guides/deployment.md), section "Security hardening for
production". Ne présentez pas la gouvernance multi-tenant ou l'audit trail complet comme déjà
opérationnels face à un client — voir la mise en garde de
[docs/onboarding.md](../../docs/onboarding.md), section 5.
