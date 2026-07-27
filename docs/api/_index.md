# API — Vue d'ensemble

Le framework expose deux surfaces d'interaction utilisateur au-dessus du même moteur
(`RAGEngine`) : une CLI (`mrag`, décrite dans [CLAUDE.md](../../CLAUDE.md)) pour l'usage
scriptable en ligne de commande, et une API REST FastAPI pour l'intégration dans une
application tierce (frontend, service backend client, chatbot). Les deux appellent
exactement le même code d'orchestration — il n'y a pas de logique dupliquée entre les deux
surfaces, seulement une différence de format d'entrée/sortie.

**Pourquoi une API REST plutôt qu'une bibliothèque Python seule ?** Beaucoup de clients ont
déjà une application (portail interne, chatbot Teams/Slack, backend existant) et veulent
appeler le RAG comme un service, sans embarquer de dépendances Python lourdes
(sentence-transformers, qdrant-client) dans leur propre stack applicative.

- [rest.md](rest.md) — référence complète des endpoints (`/health`, `/answer`,
  `/retrieve`), schémas de requête/réponse, codes d'erreur, exemples Python et `curl`.

À ce stade (pré-V4), l'API n'a pas d'authentification intégrée — voir la section
"Authentication" de [rest.md](rest.md) pour la posture recommandée en attendant `adapters/auth/`.
