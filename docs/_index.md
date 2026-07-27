# Documentation — Modular RAG Framework

Cette documentation est organisée par intention plutôt que par dossier technique : avant de
chercher un fichier précis, demandez-vous d'abord *pourquoi* vous cherchez, pas *où*. La
section ci-dessous vous oriente selon votre profil et votre besoin du moment.

**Nouveau sur ce projet ou vous ne savez pas par où commencer ?** Lisez
[onboarding.md](onboarding.md) en premier — il explique qui doit lire quoi (développeur,
lead technique, consultant en mission, profil fonctionnel, sécurité/conformité) et retrace le
parcours complet V1 → V5 en langage clair.

---

## Par intention

| Vous voulez... | Allez vers |
|---|---|
| Comprendre ce que le framework permet de faire, sans jargon technique | [onboarding.md](onboarding.md), section 3 |
| Comprendre pourquoi ce framework existe, pour convaincre un client ou un manager | [business-case.md](business-case.md) |
| Voir ce qui est livré vs planifié, version par version | [../ROADMAP.md](../ROADMAP.md) |
| Faire tourner le framework pour la première fois | [guides/getting-started.md](guides/getting-started.md) |
| Installer les dépendances et configurer l'environnement | [guides/installation.md](guides/installation.md) |
| Comprendre l'architecture en profondeur (couches, contrats, flux de données) | [architecture/_index.md](architecture/_index.md) |
| Comprendre pourquoi une décision structurelle a été prise | [adr/_index.md](adr/_index.md) |
| Ajouter un nouveau composant (chunker, retriever, générateur...) | [guides/plugin-development.md](guides/plugin-development.md) |
| Déployer en production | [guides/deployment.md](guides/deployment.md) |
| Lire ou brancher la télémétrie / les traces | [guides/observability.md](guides/observability.md) |
| Utiliser l'API REST | [api/_index.md](api/_index.md) |
| Choisir un manifest ou en créer un nouveau | [../manifests/_index.md](../manifests/_index.md) |
| Contribuer du code (setup, règles, checklist de MR) | [../CONTRIBUTING.md](../CONTRIBUTING.md) |

## Structure du dossier

```
docs/
├── onboarding.md       ← Point d'entrée : profils fonctionnels + parcours complet
├── business-case.md    ← Argumentaire business (management, delivery, commercial)
├── adr/                ← Décisions d'architecture actées, avec contexte et conséquences
├── api/                ← Référence de l'API REST
├── architecture/        ← Spécification technique complète (couches, modèles, flux, sécurité)
├── guides/              ← Guides pratiques orientés tâche (installation, déploiement, plugins...)
└── reviews/             ← Revues historiques du projet (contexte des décisions passées)
```

Chaque sous-dossier a son propre `_index.md` qui détaille son contenu plus finement.
